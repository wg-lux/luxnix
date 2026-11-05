"""Mount existing external recovery media; never partition, format or erase it."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from pydantic import BaseModel, ConfigDict

from lx_administration.storage import boot_migration as migration

MOUNT = Path("/recovery")
STATE_ROOT = MOUNT / "luxnix-state"
MIN_FREE = 1024**3  # Metadata headroom, not an application-backup size estimate.
FILESYSTEMS = {"ext4", "xfs", "btrfs"}


class Medium(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    device: str
    uuid: str
    filesystem: str
    serial: str
    size_bytes: int


def discover(spec: dict) -> list[Medium]:
    tree = json.loads(
        migration.run(
            "lsblk",
            "--json",
            "--bytes",
            "--paths",
            "--output",
            "NAME,TYPE,SIZE,FSTYPE,UUID,TRAN,RM,RO,SERIAL,MOUNTPOINTS",
        )
    )["blockdevices"]
    excluded = {d["serial"] for d in spec["disks"]}
    rows = list(migration.walk(tree))
    media = []
    for disk in tree:
        if (
            disk["type"] != "disk"
            or disk["ro"]
            or not disk["serial"]
            or disk["serial"] in excluded
            or not (disk["tran"] == "usb" or disk["rm"])
        ):
            continue
        descendants = list(migration.walk([disk]))
        if any(
            m in {"/", "/boot", "/nix", "/nix/store", "/home", "[SWAP]"}
            for row in descendants
            for m in row["mountpoints"]
        ):
            continue
        for row in descendants:
            if (
                row["ro"]
                or row["fstype"] not in FILESYSTEMS
                or not row["uuid"]
                or sum(r["uuid"] == row["uuid"] for r in rows) != 1
            ):
                continue
            media.append(
                Medium(
                    device=row["name"],
                    uuid=row["uuid"],
                    filesystem=row["fstype"],
                    serial=disk["serial"],
                    size_bytes=row["size"],
                )
            )
    return media


def select(media: list[Medium], device: str | None) -> Medium:
    chosen = media if device is None else [m for m in media if m.device == device]
    if len(chosen) != 1:
        raise migration.MigrationError(
            "Select exactly one suitable USB/removable filesystem with --device. "
            "Candidates: "
            + ", ".join(f"{m.device} ({m.serial}, {m.filesystem})" for m in media)
            + ". Blank, read-only, duplicate-UUID and unsupported filesystems "
            "are not formatted."
        )
    return chosen[0]


def privileged(program: str, *args: str) -> str:
    command = [f"/run/current-system/sw/bin/{program}", *args]
    result = subprocess.run(
        ([] if os.geteuid() == 0 else ["sudo", "--"]) + command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    # Password prompts stay on the terminal; no credentials are captured/logged.
    print(
        json.dumps({"event": "recovery_media_command", "program": program}), flush=True
    )
    return result.stdout.strip()


def mounts() -> list[dict]:
    return json.loads(
        migration.run(
            "findmnt",
            "--json",
            "--list",
            "--output",
            "TARGET,SOURCE,FSTYPE,UUID,OPTIONS",
        )
    )["filesystems"]


def verify_mount(medium: Medium, excluded: set[int]) -> int:
    records = [r for r in mounts() if r["target"] == str(MOUNT)]
    if len(records) != 1:
        raise migration.MigrationError("Recovery mount is missing or ambiguous")
    record = records[0]
    if (
        record["uuid"] != medium.uuid
        or record["fstype"] != medium.filesystem
        or "ro" in record["options"].split(",")
    ):
        raise migration.MigrationError(
            "Recovery mount identity or write access differs"
        )
    if any(
        migration.device_disks(d) & excluded
        for d in migration.filesystem_devices(record)
    ):
        raise migration.MigrationError(
            "Recovery filesystem overlaps a target or running-system disk"
        )
    usage = os.statvfs(MOUNT)
    available = usage.f_bavail * usage.f_frsize
    if available < MIN_FREE:
        raise migration.MigrationError(
            "Recovery filesystem needs at least 1 GiB free for setup metadata"
        )
    return available


def setup(spec: dict, state: Path, *, apply: bool, device: str | None = None) -> None:
    if state.parent != STATE_ROOT:
        raise migration.MigrationError(
            "setup-media requires boot_storage.state_root: /recovery/luxnix-state"
        )
    medium = select(discover(spec), device)
    print(medium.model_dump_json(indent=2))
    if not apply:
        print(
            "Preview only. --apply mounts the existing filesystem, "
            "checks free space and creates the plan."
        )
        return
    migration.source_identity(Path(spec["checkout"]))
    if (
        privileged("cat", str(migration.DMI_UUID)).lower()
        != spec["hardware_uuid"].lower()
    ):
        raise migration.MigrationError("This is not the selected host's hardware")
    excluded = set().union(*(migration.device_disks(d["path"]) for d in spec["disks"]))
    root = next(r for r in mounts() if r["target"] == "/")
    if root["source"].startswith("/dev/"):
        for member in migration.filesystem_devices(root):
            excluded.update(migration.device_disks(member))
    if migration.device_disks(medium.device) & excluded:
        raise migration.MigrationError(
            "Recovery device overlaps a target or running-system disk"
        )
    if MOUNT.resolve() != MOUNT or (MOUNT.exists() and not MOUNT.is_dir()):
        raise migration.MigrationError("Unsafe /recovery path")
    mounted = any(r["target"] == str(MOUNT) for r in mounts())
    if not mounted:
        if MOUNT.exists() and any(MOUNT.iterdir()):
            raise migration.MigrationError(
                "Refusing to hide existing files under /recovery"
            )
        if any(r["target"].startswith(str(MOUNT) + "/") for r in mounts()):
            raise migration.MigrationError("Refusing to cover nested recovery mounts")
        privileged("mkdir", "-p", str(MOUNT))
        if select(discover(spec), medium.device) != medium:
            raise migration.MigrationError(
                "External drive identity changed; no mount attempted"
            )
        privileged("mount", "-o", "nosuid,nodev", "--", medium.device, str(MOUNT))
    if select(discover(spec), medium.device) != medium:
        raise migration.MigrationError(
            "External drive identity changed; no state prepared"
        )
    available = verify_mount(medium, excluded)
    print(f"Recovery free space: {available // 1024**2} MiB")
    if STATE_ROOT.exists() or STATE_ROOT.is_symlink():
        migration.private_path(STATE_ROOT, directory=True)
    else:
        # Never recursively chown an existing recovery directory or its contents.
        privileged(
            "install",
            "-d",
            "-m",
            "0700",
            "-o",
            str(os.geteuid()),
            "-g",
            str(os.getegid()),
            str(STATE_ROOT),
        )
        migration.private_path(STATE_ROOT, directory=True)
    verify_mount(medium, excluded)
