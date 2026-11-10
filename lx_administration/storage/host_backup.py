"""Keep an encrypted, consistent copy of this host's data on the recovery drive.

Each run captures read-only Btrfs snapshots while the application writers are
briefly stopped (snapshot.py), then updates one encrypted container on the recovery
drive with rsync: changed files are copied and removed files are removed, so the
backup always matches the newest capture. A checksum comparison against the
snapshots verifies the copy. The container is LUKS2 and opens with a random key kept
in the encrypted custody, so no data reaches the recovery drive unencrypted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from lx_administration.storage import boot_migration as migration
from lx_administration.storage import recovery_media, secret_preflight
from lx_administration.utils.file_operations import atomic_create_file

GIB = 1024**3
SNAPSHOTS = Path("/var/lib/luxnix-migration-snapshots")
PREFIX = "backup-"
MOUNT_ROOT = Path("/run/luxnix-backup")
SUMMARY = "host-backup.json"
MANIFEST = "luxnix-backup.json"
RSYNC = ("-aHAX", "--numeric-ids", "--delete", "--one-file-system")
TRUSTED_TOOLS = ("/nix/store/", "/run/current-system/")


def tool(name: str) -> str:
    """An immutable executable for root; sudo would otherwise reset PATH."""
    found = name if os.path.isabs(name) else shutil.which(name)
    if found is None:
        raise migration.MigrationError(
            f"{name} is required for the backup", fix="run from the devenv shell"
        )
    real = os.path.realpath(found)
    if not real.startswith(TRUSTED_TOOLS):
        raise migration.MigrationError(f"{name} is not from the Nix store: {real}")
    return real


def as_root(*command: str, capture: bool = False) -> str:
    result = subprocess.run(
        [*secret_preflight.root_prefix(), tool(command[0]), *command[1:]],
        text=True,
        stdout=subprocess.PIPE if capture else None,
        check=False,
    )
    if result.returncode:
        raise migration.MigrationError(
            f"{Path(command[0]).name} failed (exit {result.returncode}) during the "
            "backup; the previous backup stays usable and a rerun continues it"
        )
    return result.stdout or ""


def container(host: str) -> Path:
    return recovery_media.MOUNT / f"luxnix-backup-{host}.luks"


def mapping(host: str) -> str:
    return f"luxnix-backup-{host}"


def ensure_key(custody: Path, host: str) -> Path:
    """The container key lives only inside the encrypted custody."""
    key = custody / host / "host-backup.key"
    if not key.exists():
        key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_create_file(
            destination=key, content=[os.urandom(64)], file_mode=0o400
        )
    migration.private_path(key)
    return key


def needed_bytes() -> int:
    """Room for everything on the root filesystem, with a quarter to spare."""
    info = os.statvfs("/")
    used = (info.f_blocks - info.f_bfree) * info.f_frsize
    return int(used * 1.25) + 4 * GIB


def free_bytes(path: Path) -> int:
    info = os.statvfs(path)
    return info.f_bavail * info.f_frsize


def require_room(extra: int) -> None:
    if free_bytes(recovery_media.MOUNT) < extra:
        raise migration.MigrationError(
            f"The recovery drive needs {extra // GIB} GiB more free space for the "
            "backup",
            fix="free space on the recovery drive or use a larger one, then rerun",
        )


def loop_device(host: str) -> str:
    status = as_root("cryptsetup", "status", mapping(host), capture=True)
    for line in status.splitlines():
        name, _, value = line.strip().partition(":")
        if name == "device":
            return value.strip()
    raise migration.MigrationError("Cannot find the backup container's loop device")


def open_container(host: str, key: Path, needed: int) -> Path:
    """Open the container, creating it on first use and growing it when needed."""
    path, device = container(host), f"/dev/mapper/{mapping(host)}"
    mount = MOUNT_ROOT / host
    if not secret_preflight.exists(path):
        require_room(needed)
        print(f"Creating the encrypted backup container {path}.")
        as_root("truncate", "-s", str(needed), str(path))
        as_root(
            "cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode",
            "--key-file", str(key), str(path),
        )  # fmt: skip
        as_root("cryptsetup", "open", "--key-file", str(key), str(path), mapping(host))
        as_root("mkfs.ext4", "-q", "-L", "luxnix-backup", device)
    else:
        if secret_preflight.privileged("cryptsetup", "isLuks", str(path)).returncode:
            raise migration.MigrationError(
                f"{path} is not a LUKS container; move it aside, then rerun"
            )
        if not Path(device).exists():
            as_root(
                "cryptsetup", "open", "--key-file", str(key), str(path), mapping(host)
            )
    grow = needed - int(as_root("stat", "-c", "%s", str(path), capture=True))
    if grow > 0:
        require_room(grow)
        print(f"Growing the backup container by {grow // GIB + 1} GiB.")
        as_root("truncate", "-s", str(needed), str(path))
        as_root("losetup", "-c", loop_device(host))
        as_root("cryptsetup", "resize", "--key-file", str(key), mapping(host))
    as_root("mkdir", "-p", str(mount))
    if secret_preflight.privileged("mountpoint", "-q", str(mount)).returncode:
        as_root("mount", "-o", "nosuid,nodev", device, str(mount))
    if grow > 0:
        as_root("resize2fs", device)
    return mount


def close_container(host: str) -> None:
    mount = MOUNT_ROOT / host
    if not secret_preflight.privileged("mountpoint", "-q", str(mount)).returncode:
        as_root("umount", str(mount))
    if Path("/dev/mapper", mapping(host)).exists():
        as_root("cryptsetup", "close", mapping(host))


def capture(host: str) -> dict:
    """A consistent read-only snapshot set; snapshot.py restarts the writers."""
    identifier = PREFIX + time.strftime("%Y%m%dt%H%M%S")
    print(
        "Taking a consistent snapshot: the application services stop for a moment "
        "and start again automatically."
    )
    output = as_root(
        sys.executable,
        str(Path(__file__).with_name("snapshot.py")),
        host,
        identifier,
        capture=True,
    )
    report = json.loads(output.strip().splitlines()[-1])
    if not report.get("complete") or report.get("identifier") != identifier:
        raise migration.MigrationError("The snapshot did not complete")
    return report


def copy(report: dict, mount: Path) -> None:
    for item in report["snapshots"]:
        source, target = item["snapshot"].rstrip("/") + "/", mount / item["name"]
        print(f"Updating the backup of {item['source']}...")
        as_root("mkdir", "-p", str(target))
        as_root("rsync", *RSYNC, "--info=progress2", source, f"{target}/")


def verify(report: dict, mount: Path) -> None:
    """Every file's checksum must equal the snapshot's; any difference stops."""
    for item in report["snapshots"]:
        source, target = item["snapshot"].rstrip("/") + "/", mount / item["name"]
        print(f"Verifying the backup of {item['source']} by checksum...")
        changes = as_root(
            "rsync", *RSYNC, "--dry-run", "--checksum", "--itemize-changes",
            source, f"{target}/", capture=True,
        )  # fmt: skip
        if changes.strip():
            raise migration.MigrationError(
                f"The backup of {item['source']} differs from its snapshot; rerun "
                "to update it"
            )


def prune(current: str) -> None:
    """Keep only the newest backup snapshot set on the host."""
    listing = as_root(
        "find", str(SNAPSHOTS), "-mindepth", "1", "-maxdepth", "1",
        "-name", f"{PREFIX}*", capture=True,
    )  # fmt: skip
    for path in map(Path, listing.split()):
        if path.name == current or path.parent != SNAPSHOTS:
            continue
        plan = json.loads(secret_preflight.read_private(path / "plan.json"))
        if not (plan.get("complete") and plan.get("state") == "complete"):
            continue
        for item in plan["snapshots"]:
            snapshot = Path(item["snapshot"])
            if snapshot.name != item["name"] or snapshot.parent.name != path.name:
                raise migration.MigrationError(f"Unexpected snapshot path {snapshot}")
            as_root("btrfs", "subvolume", "delete", str(snapshot))
        as_root("rm", "-rf", "--one-file-system", str(path))


def run(spec: dict, state: Path, custody: Path) -> dict:
    """Capture, upsert and verify; returns the guide's backup outcome."""
    host = spec["host"]
    print(
        f"\nBacking up {host} to the recovery drive, encrypted. Only changes since "
        "the last backup are copied."
    )
    key = ensure_key(custody, host)
    mount = open_container(host, key, needed_bytes())
    try:
        report = capture(host)
        copy(report, mount)
        verify(report, mount)
        summary = {
            "schema_version": 1,
            "host": host,
            "container": str(container(host)),
            "snapshot": report["identifier"],
            "components": [item["source"] for item in report["snapshots"]],
            "verified_at": time.time(),
        }
        migration.atomic_json(state / SUMMARY, summary)
        as_root(
            "install", "-m", "0600", str(state / SUMMARY), str(mount / MANIFEST)
        )
    finally:
        close_container(host)
    prune(report["identifier"])
    return {
        "status": "copy-verified",
        "accepted_by": None,
        "location": str(container(host)),
        "restore_test": None,
        "verification": "checksum-compared",
    }
