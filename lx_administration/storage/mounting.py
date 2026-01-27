from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from .manager import StorageManager

DEFAULT_BY_ID_PATH = Path("/dev/disk/by-id")


def external_drive_requires_mount(storage: StorageManager) -> bool:
    """Return True when an external persisting drive still needs to be mounted."""

    if not storage.storage_persisting_external_drive:
        return False
    return not storage.storage_persisting_mount_point.is_mount()


def find_device_by_serial(
    serial: str, by_id_path: Path = DEFAULT_BY_ID_PATH
) -> Path | None:
    """Find the block device symlink that contains the given serial in /dev/disk/by-id."""

    if not serial:
        return None
    if not by_id_path.exists():
        return None

    for entry in by_id_path.iterdir():
        if serial in entry.name:
            resolved = entry.resolve()
            if resolved.exists():
                return resolved

    return None


def drive_with_serial_available(
    storage: StorageManager, by_id_path: Path = DEFAULT_BY_ID_PATH
) -> Path | None:
    """Return the block device Path if the configured serial is present and not mounted."""

    serial = storage.storage_persisting_hdd_id
    if serial is None:
        return None

    device = find_device_by_serial(serial, by_id_path=by_id_path)
    if device is None:
        return None

    if storage.storage_persisting_mount_point.is_mount():
        return None

    return device


def mount_drive(
    device: Path,
    mount_point: Path,
    filesystem: str | None = None,
    options: Sequence[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Mount the given block device at mount_point using the system mount command."""

    mount_point.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = ["mount"]
    if filesystem:
        cmd.extend(["-t", filesystem])
    if options:
        cmd.extend(["-o", ",".join(options)])

    cmd.extend([device.as_posix(), mount_point.as_posix()])
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def unmount_drive(target: Path) -> subprocess.CompletedProcess[str]:
    """Unmount the filesystem mounted at target using the system umount command."""

    return subprocess.run(
        ["umount", target.as_posix()], check=True, capture_output=True, text=True
    )
