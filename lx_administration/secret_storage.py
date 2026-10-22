"""Fail before secret writes unless the destination has an encrypted boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


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


def encrypted_storage(path: Path, *, allow_runtime: bool = False) -> None:
    """Require every backing-device branch to cross an encryption mapping.

    The caller must retain mount ordering and protect parent directories against
    concurrent replacement. This probe neither unlocks nor changes storage.
    """
    if not path.is_absolute() or ".." in path.parts or path.resolve() != path:
        raise ValueError("Secret storage requires absolute paths without symlinks")
    swap_names = subprocess.check_output(
        ["swapon", "--show=NAME", "--noheadings", "--raw"],
        stderr=subprocess.DEVNULL,
    )

    if swap_names.strip():
        raise ValueError("Plaintext secret handling requires disabled swap")
    existing = path
    while not existing.exists():
        existing = existing.parent
    mount = _probe(
        "findmnt", "--json", "--target", str(existing), "--output", "SOURCE,FSTYPE"
    ) #TODO Extend towards a stricter approach where filesystem types are valid
    if not isinstance(mount, dict):
        raise ValueError("Invalid secret storage mount probe")
    filesystems = mount.get("filesystems")
    if not isinstance(filesystems, list) or len(filesystems) != 1:
        raise ValueError("Secret storage must resolve to one mounted filesystem")
    filesystem = filesystems[0]
    if not isinstance(filesystem, dict):
        raise ValueError("Invalid secret storage filesystem")
    if allow_runtime and filesystem.get("fstype") == "tmpfs":
        return
    if filesystem.get("fstype") in {"tmpfs", "ramfs", "overlay"}:
        raise ValueError("Persistent secrets require encrypted block storage")
    source = filesystem.get("source")
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
