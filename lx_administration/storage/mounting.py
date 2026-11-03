from __future__ import annotations

import os
import json
import re
import stat
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .manager import StorageManager
from lx_administration.secret_storage import encrypted_storage, _require_encrypted_device

DEFAULT_BY_ID_PATH = Path("/dev/disk/by-id")


def external_drive_requires_mount(storage: StorageManager) -> bool:
    """Return True when an external persisting drive still needs to be mounted."""

    if not storage.storage_persisting_external_drive:
        return False
    device = find_device_by_serial(storage.storage_persisting_hdd_id or "")
    if storage.storage_persisting_mount_point.is_mount():
        if device is None:
            raise ValueError("Cannot verify the configured mounted device")
        verify_mount(device, storage.storage_persisting_mount_point)
        return False
    return True


def find_device_by_serial(
    serial: str, by_id_path: Path = DEFAULT_BY_ID_PATH
) -> Path | None:
    """Select one real block device whose reported hardware serial matches exactly."""
    if not serial or not by_id_path.is_dir():
        return None
    candidates = set()
    examined = set()
    for entry in by_id_path.iterdir():
        # A serial selects a device, never an arbitrary numbered partition.
        if not entry.is_symlink() or re.search(r"-part[0-9]+$", entry.name):
            continue
        try:
            resolved = entry.resolve(strict=True)
        except FileNotFoundError:
            continue
        if resolved in examined or not stat.S_ISBLK(resolved.stat().st_mode):
            continue
        examined.add(resolved)
        records = json.loads(subprocess.check_output(
            ["lsblk", "--json", "--paths", "--output", "NAME,TYPE,SERIAL,FSTYPE", str(resolved)],
            text=True, stderr=subprocess.DEVNULL))["blockdevices"]
        if len(records) != 1:
            raise ValueError("Ambiguous block device serial probe")
        if records[0].get("serial") != serial:
            continue
        def unlocked_filesystems(node):
            if node.get("type") == "crypt" and node.get("fstype") not in (None, "", "crypto_LUKS"):
                if node.get("children"):
                    raise ValueError("Encrypted storage has unsupported dependent mappings")
                yield Path(node["name"]).resolve(strict=True)
            for child in node.get("children", []):
                yield from unlocked_filesystems(child)
        mappings = set(unlocked_filesystems(records[0]))
        if len(mappings) > 1:
            raise ValueError("Multiple encrypted filesystems have the configured serial")
        selected = next(iter(mappings), resolved)
        if not stat.S_ISBLK(selected.stat().st_mode):
            raise ValueError("Selected encrypted filesystem is not a block device")
        candidates.add(selected)
    if len(candidates) > 1:
        raise ValueError("Multiple devices have the configured serial")
    return next(iter(candidates), None)


def verify_mount(device: Path, mount_point: Path) -> None:
    records = json.loads(subprocess.check_output(
        ["findmnt", "--json", "--mountpoint", str(mount_point), "--output", "SOURCE"],
        text=True, stderr=subprocess.DEVNULL))["filesystems"]
    if len(records) != 1:
        raise ValueError("Ambiguous persisting storage mount")
    source = Path(records[0]["source"].split("[", 1)[0])
    if source.stat().st_rdev != device.stat().st_rdev:
        raise ValueError("Mounted persisting storage is not the configured device")
    encrypted_storage(mount_point)


def drive_with_serial_available(
    storage: StorageManager, by_id_path: Path = DEFAULT_BY_ID_PATH
) -> Path | None:
    """Return the configured block device when present and not mounted."""

    serial = storage.storage_persisting_hdd_id
    if serial is None:
        return None

    device = find_device_by_serial(serial, by_id_path=by_id_path)
    if device is None:
        return None

    if storage.storage_persisting_mount_point.is_mount():
        verify_mount(device, storage.storage_persisting_mount_point)
        return None

    return device


def mount_drive(
    device: Path,
    mount_point: Path,
    filesystem: str | None = None,
    options: Sequence[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Mount the given block device at mount_point using the system mount command."""

    if not stat.S_ISBLK(device.stat().st_mode):
        raise ValueError("Mount source must be a block device")
    if not mount_point.is_absolute() or mount_point.resolve() != mount_point:
        raise ValueError("Mountpoint must be absolute without symlinks")
    _require_encrypted_device(str(device))
    if mount_point.is_mount():
        verify_mount(device, mount_point)
        raise ValueError("Persisting storage is already mounted")
    mount_point.mkdir(parents=True, exist_ok=True)

    mount_bin = Path(
        shutil.which("mount") or "/run/current-system/sw/bin/mount"
    ).resolve()

    cmd: list[str] = [mount_bin.as_posix()]
    if filesystem:
        cmd.extend(["-t", filesystem])
    if options:
        cmd.extend(["-o", ",".join(options)])

    cmd.extend([device.as_posix(), mount_point.as_posix()])

    if os.geteuid() != 0:
        cmd = ["sudo"] + cmd

    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    verify_mount(device, mount_point)
    return result


def unmount_drive(target: Path) -> subprocess.CompletedProcess[str]:
    """Unmount the filesystem mounted at target using the system umount command."""

    umount_bin = Path(
        shutil.which("umount") or "/run/current-system/sw/bin/umount"
    ).resolve()

    cmd = [umount_bin.as_posix(), target.as_posix()]

    if os.geteuid() != 0:
        cmd = ["sudo"] + cmd

    return subprocess.run(cmd, check=True, capture_output=True, text=True)
