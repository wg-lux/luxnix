"""Fail before secret writes unless the destination has an encrypted boundary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

SYS_BLOCK = Path("/sys/block")
BTRFS_SYSFS = Path("/sys/fs/btrfs")
_ZRAM_DEVICE = re.compile(r"/dev/(zram[0-9]+)")


def _probe(*command: str) -> object:
    return json.loads(subprocess.check_output(command, stderr=subprocess.DEVNULL))


def _protected(device: object) -> bool:
    if not isinstance(device, dict):
        return False
    if device.get("type") == "crypt":
        return True
    children = device.get("children")
    return (
        isinstance(children, list)
        and bool(children)
        and all(_protected(child) for child in children)
    )


def _mounted_filesystem(path: Path) -> dict:
    mount = _probe(
        "findmnt", "--json", "--target", str(path), "--output", "SOURCE,FSTYPE,UUID"
    )
    if not isinstance(mount, dict):
        raise ValueError("Invalid secret storage mount probe")
    filesystems = mount.get("filesystems")
    if not isinstance(filesystems, list) or not filesystems:
        raise ValueError("Secret storage must resolve to one mounted filesystem")
    filesystem = filesystems[0]
    if not isinstance(filesystem, dict):
        raise ValueError("Invalid secret storage filesystem")
    # systemd's recursive sandbox bind mounts can repeat the same target.
    # Accept only identical source/type reports; ambiguous storage fails closed.
    if any(candidate != filesystem for candidate in filesystems[1:]):
        raise ValueError("Secret storage must resolve to one mounted filesystem")
    return filesystem


def _require_encrypted_device(source: object) -> None:
    if not isinstance(source, str) or not source.startswith("/dev/"):
        raise ValueError("Secret storage must be backed by an encrypted device")
    devices = _probe(
        "lsblk", "--json", "--inverse", "--output", "NAME,TYPE", source.split("[", 1)[0]
    )
    if not isinstance(devices, dict):
        raise ValueError("Invalid secret storage device probe")
    blockdevices = devices.get("blockdevices")
    if (
        not isinstance(blockdevices, list)
        or not blockdevices
        or not all(_protected(device) for device in blockdevices)
    ):
        raise ValueError("Secret storage is not backed entirely by encrypted devices")


def filesystem_devices(filesystem: dict) -> list[str]:
    """Resolve every mounted Btrfs member from kernel evidence, never SOURCE alone."""
    source = filesystem.get("source")
    if not isinstance(source, str) or not source.startswith("/dev/"):
        raise ValueError("Storage must be backed by a block device")
    source = source.split("[", 1)[0]
    if filesystem.get("fstype") != "btrfs":
        return [source]
    identifier = filesystem.get("uuid")
    if not isinstance(identifier, str) or str(uuid.UUID(identifier)) != identifier:
        raise ValueError("Invalid mounted Btrfs UUID")
    root = BTRFS_SYSFS / identifier
    members = sorted((root / "devices").iterdir())
    # Missing devices have devinfo records but no devices symlink in sysfs.
    metadata = list((root / "devinfo").iterdir())
    if not members or len(members) != len(metadata):
        raise ValueError("Incomplete Btrfs member evidence")
    for device in metadata:
        if (not device.is_dir() or not re.fullmatch(r"[0-9]+", device.name)
                or (device / "missing").read_text().strip() != "0"):
            raise ValueError("Missing or invalid Btrfs member")
    numbers = set()
    devices = []
    for member in members:
        if not member.is_dir():
            raise ValueError("Invalid Btrfs member evidence")
        number = (member / "dev").read_text().strip()
        if not re.fullmatch(r"[1-9][0-9]*:(?:0|[1-9][0-9]*)", number):
            raise ValueError("Missing or invalid Btrfs member device")
        major, minor = map(int, number.split(":"))
        device = f"/dev/block/{number}"
        info = os.stat(device)
        if (not stat.S_ISBLK(info.st_mode)
                or (os.major(info.st_rdev), os.minor(info.st_rdev)) != (major, minor)
                or info.st_rdev in numbers):
            raise ValueError("Invalid Btrfs member block identity")
        numbers.add(info.st_rdev)
        devices.append(device)
    if ".." in Path(source).parts:
        raise ValueError("Invalid Btrfs source device")
    info = os.stat(source)
    if not stat.S_ISBLK(info.st_mode) or info.st_rdev not in numbers:
        raise ValueError("Btrfs source does not match its kernel member set")
    return devices


def _require_encrypted_filesystem(filesystem: dict) -> None:
    for device in filesystem_devices(filesystem):
        _require_encrypted_device(device)


def _zram_writeback_disabled(device: str) -> bool:
    try:
        backing = (SYS_BLOCK / device / "backing_dev").read_text().strip()
    except FileNotFoundError:
        # Kernels without CONFIG_ZRAM_WRITEBACK cannot page zram out to disk.
        return True
    return backing == "none"


def _require_protected_swap() -> None:
    """Reject swap that could page plaintext secrets onto unencrypted storage.

    RAM-only zram and swap backed entirely by encrypted block devices are
    accepted; anything else, including zram writeback, fails closed.
    """
    output = subprocess.check_output(
        ["swapon", "--show=NAME,TYPE", "--noheadings", "--raw"],
        stderr=subprocess.DEVNULL,
        text=True,
    )
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 2:
            raise ValueError("Invalid swap probe")
        name, kind = fields
        zram = _ZRAM_DEVICE.fullmatch(name)
        if kind == "partition" and zram:
            if not _zram_writeback_disabled(zram.group(1)):
                raise ValueError("Plaintext secret handling forbids zram writeback")
        elif kind == "partition":
            _require_encrypted_device(name)
        elif kind == "file":
            _require_encrypted_filesystem(_mounted_filesystem(Path(name)))
        else:
            raise ValueError("Plaintext secret handling requires encrypted swap")


def encrypted_storage(path: Path, *, allow_runtime: bool = False) -> None:
    """Require every backing-device branch to cross an encryption mapping.

    The caller must retain mount ordering and protect parent directories against
    concurrent replacement. This probe neither unlocks nor changes storage.
    """
    if not path.is_absolute() or ".." in path.parts or path.resolve() != path:
        raise ValueError("Secret storage requires absolute paths without symlinks")
    _require_protected_swap()
    existing = path
    while not existing.exists():
        existing = existing.parent
    filesystem = _mounted_filesystem(existing)
    if allow_runtime and filesystem.get("fstype") == "tmpfs":
        return
    if filesystem.get("fstype") in {"tmpfs", "ramfs", "overlay"}:
        raise ValueError("Persistent secrets require encrypted block storage")
    _require_encrypted_filesystem(filesystem)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-runtime", action="store_true")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        for path in args.paths:
            encrypted_storage(path, allow_runtime=args.allow_runtime)
    except (ValueError, OSError, subprocess.CalledProcessError):
        parser.exit(1, "ERROR: Secret storage boundary verification failed.\n")


if __name__ == "__main__":
    main()
