"""Encrypted host backup on the recovery drive; never touches real storage."""

import json
from pathlib import Path
import stat
import sys

import pytest

from lx_administration.storage import boot_migration as migration
from lx_administration.storage import host_backup as backup

GIB = backup.GIB
BASE = "/var/lib/luxnix-migration-snapshots/backup-20261110t120000"
SNAPSHOT = {
    "complete": True,
    "state": "complete",
    "identifier": "backup-20261110t120000",
    "snapshots": [
        {
            "source": "/",
            "name": "root",
            "snapshot": f"{BASE}/root",
        },
        {
            "source": "/home",
            "name": "home",
            "snapshot": f"{BASE}/home",
        },
    ],
}


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """Records every root command; reports a configurable container size."""
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o700)
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    world = {
        "container": False,
        "size": 0,
        "mounted": False,
        "open": False,
        "verify": "",
        "listing": "",
        "plans": {},
    }
    calls = []

    def as_root(*command, capture=False):
        calls.append(command)
        name = Path(command[0]).name
        if name == "cryptsetup" and command[1] == "luksFormat":
            world["container"] = True
        if name == "cryptsetup" and command[1] == "open":
            world["open"] = True
        if name == "cryptsetup" and command[1] == "close":
            world["open"] = False
        if name == "cryptsetup" and command[1] == "status":
            return "  type:    LUKS2\n  device:  /dev/loop7\n"
        if name == "truncate":
            world["size"] = int(command[2])
        if name == "mount":
            world["mounted"] = True
        if name == "umount":
            world["mounted"] = False
        if name == "stat":
            return str(world["size"])
        if name == "rsync" and "--dry-run" in command:
            return world["verify"]
        if name == "find":
            return world["listing"]
        if command[0] == sys.executable:
            # snapshot.py <host> <identifier>; the report names that identifier.
            world["identifier"] = command[3]
            report = SNAPSHOT | {"identifier": command[3]}
            return "progress\n" + json.dumps(report) + "\n"
        return ""

    class Result:
        def __init__(self, code):
            self.returncode = code

    def privileged(*command):
        if command[0] == "cryptsetup":
            return Result(0)
        if command[0] == "mountpoint":
            return Result(0 if world["mounted"] else 1)
        return Result(1)

    monkeypatch.setattr(backup, "as_root", as_root)
    monkeypatch.setattr(backup.secret_preflight, "privileged", privileged)
    monkeypatch.setattr(
        backup.secret_preflight, "exists", lambda path: world["container"]
    )
    monkeypatch.setattr(
        backup.secret_preflight,
        "read_private",
        lambda path: json.dumps(world["plans"][path.parent.name]).encode(),
    )
    monkeypatch.setattr(backup.recovery_media, "MOUNT", recovery)
    monkeypatch.setattr(backup, "MOUNT_ROOT", tmp_path / "run")
    monkeypatch.setattr(backup, "needed_bytes", lambda: 100 * GIB)
    monkeypatch.setattr(backup, "free_bytes", lambda path: 500 * GIB)
    monkeypatch.setattr(backup.Path, "exists", _exists(world))
    monkeypatch.setattr(migration, "private_path", lambda *a, **k: None)
    return {"state": state, "custody": custody, "world": world, "calls": calls}


def _exists(world):
    real = Path.exists

    def exists(path, *args, **kwargs):
        if str(path).startswith("/dev/mapper/luxnix-backup-"):
            return world["open"]
        return real(path, *args, **kwargs)

    return exists


def names(calls):
    return [
        "snapshot" if command[0] == sys.executable else Path(command[0]).name
        for command in calls
    ]


def test_first_backup_creates_an_encrypted_container_then_copies_and_verifies(
    machine,
):
    result = backup.run({"host": "gc-09"}, machine["state"], machine["custody"])
    calls = machine["calls"]
    # Encryption exists before any data is written to the recovery drive.
    order = names(calls)
    assert order.index("cryptsetup") < order.index("mkfs.ext4") < order.index("rsync")
    format_call = next(c for c in calls if c[:2] == ("cryptsetup", "luksFormat"))
    key = machine["custody"] / "host-backup-gc-09.key"
    assert str(key) in format_call
    assert stat.S_IMODE(key.stat().st_mode) == 0o400 and len(key.read_bytes()) == 64
    copies = [c for c in calls if c[0] == "rsync" and "--dry-run" not in c]
    assert [c[-1] for c in copies] == [
        f"{backup.MOUNT_ROOT}/gc-09/root/",
        f"{backup.MOUNT_ROOT}/gc-09/home/",
    ]
    assert all("--delete" in c and "--one-file-system" in c for c in copies)
    checks = [c for c in calls if c[0] == "rsync" and "--dry-run" in c]
    assert len(checks) == 2 and all("--checksum" in c for c in checks)
    # The snapshot is taken after the container is ready and before copying.
    assert order.index("mount") < order.index("snapshot") < order.index("rsync")
    assert names(calls)[-3:] == ["umount", "cryptsetup", "find"]
    assert result == {
        "status": "copy-verified",
        "accepted_by": None,
        "location": str(backup.container("gc-09")),
        "restore_test": None,
        "verification": "checksum-compared",
    }
    summary = json.loads((machine["state"] / backup.SUMMARY).read_text())
    assert summary["snapshot"] == machine["world"]["identifier"]
    assert summary["snapshot"].startswith(backup.PREFIX)
    assert summary["components"] == ["/", "/home"]


def test_later_runs_update_the_same_container_without_reformatting(machine):
    world = machine["world"]
    world.update(container=True, size=100 * GIB)
    key = machine["custody"] / "host-backup-gc-09.key"
    key.write_bytes(b"k" * 64)
    key.chmod(0o400)
    backup.run({"host": "gc-09"}, machine["state"], machine["custody"])
    calls = machine["calls"]
    assert not [c for c in calls if "luksFormat" in c or c[0] == "mkfs.ext4"]
    assert ("cryptsetup", "open", "--key-file", str(key)) == next(
        c for c in calls if c[:2] == ("cryptsetup", "open")
    )[:4]
    assert key.read_bytes() == b"k" * 64
    assert not [c for c in calls if c[0] in {"losetup", "resize2fs"}]


def test_a_growing_machine_grows_the_container_in_place(machine):
    world = machine["world"]
    backup.ensure_key(machine["custody"], "gc-09")
    world.update(container=True, size=60 * GIB)
    backup.run({"host": "gc-09"}, machine["state"], machine["custody"])
    order = names(machine["calls"])
    assert ("losetup", "-c", "/dev/loop7") in machine["calls"]
    assert order.index("losetup") < order.index("mount") < order.index("resize2fs")
    assert world["size"] == 100 * GIB


def test_too_little_space_stops_before_anything_is_written(machine, monkeypatch):
    monkeypatch.setattr(backup, "free_bytes", lambda path: 10 * GIB)
    with pytest.raises(migration.MigrationError, match="needs 100 GiB more"):
        backup.run({"host": "gc-09"}, machine["state"], machine["custody"])
    assert not [c for c in machine["calls"] if c[0] in {"truncate", "cryptsetup"}]


def test_a_checksum_difference_fails_and_still_closes_the_container(machine):
    machine["world"]["verify"] = ">fc.T...... etc/changed\n"
    with pytest.raises(migration.MigrationError, match="differs from its snapshot"):
        backup.run({"host": "gc-09"}, machine["state"], machine["custody"])
    assert not machine["world"]["mounted"] and not machine["world"]["open"]
    assert not (machine["state"] / backup.SUMMARY).exists()
    assert "find" not in names(machine["calls"])


def test_only_the_newest_backup_snapshots_stay_on_the_host(machine):
    world = machine["world"]
    base = backup.SNAPSHOTS
    world["listing"] = "\n".join(
        str(base / name)
        for name in (
            "backup-20261101t080000",
            "backup-20261105t080000",
        )
    )

    def plan(name, complete=True):
        return {
            "complete": complete,
            "state": "complete" if complete else "in_progress",
            "snapshots": [{"name": "root", "snapshot": str(base / name / "root")}],
        }

    world["plans"] = {
        "backup-20261101t080000": plan("backup-20261101t080000"),
        "backup-20261105t080000": plan("backup-20261105t080000", complete=False),
    }
    backup.run({"host": "gc-09"}, machine["state"], machine["custody"])
    deleted = [c for c in machine["calls"] if c[:3] == ("btrfs", "subvolume", "delete")]
    assert deleted == [
        ("btrfs", "subvolume", "delete", str(base / "backup-20261101t080000/root"))
    ]
    removed = [c for c in machine["calls"] if c[0] == "rm"]
    assert removed == [
        ("rm", "-rf", "--one-file-system", str(base / "backup-20261101t080000"))
    ]


def test_pruning_refuses_snapshot_paths_outside_their_set(machine):
    world = machine["world"]
    world["listing"] = str(backup.SNAPSHOTS / "backup-20261101t080000")
    world["plans"] = {
        "backup-20261101t080000": {
            "complete": True,
            "state": "complete",
            "snapshots": [{"name": "root", "snapshot": "/home"}],
        }
    }
    with pytest.raises(migration.MigrationError, match="Unexpected snapshot path"):
        backup.run({"host": "gc-09"}, machine["state"], machine["custody"])
    assert not [c for c in machine["calls"] if c[0] == "btrfs"]


def test_root_commands_use_immutable_store_tools(monkeypatch, tmp_path):
    fake = tmp_path / "rsync"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(backup.migration_boot.shutil, "which", lambda name: str(fake))
    with pytest.raises(
        migration.MigrationError, match="from the Nix store is required"
    ):
        backup.tool("rsync")
    monkeypatch.setattr(backup.migration_boot.shutil, "which", lambda name: None)
    with pytest.raises(
        migration.MigrationError, match="required; use the devenv shell"
    ):
        backup.tool("rsync")


def test_the_backup_key_lives_in_the_operator_owned_custody_root(machine):
    # Per-host custody folders may be root-owned from earlier sudo copies.
    root_folder = machine["custody"] / "gc-09"
    root_folder.mkdir(mode=0o555)
    key = backup.ensure_key(machine["custody"], "gc-09")
    assert key == machine["custody"] / "host-backup-gc-09.key"
    assert stat.S_IMODE(key.stat().st_mode) == 0o400
    root_folder.chmod(0o700)


def test_existing_legacy_key_is_reused_without_replacement(machine):
    legacy = machine["custody"] / "gc-09" / "host-backup.key"
    legacy.parent.mkdir(mode=0o700)
    legacy.write_bytes(b"old" * 21 + b"!")
    legacy.chmod(0o400)
    machine["world"].update(container=True, size=100 * GIB)
    backup.run({"host": "gc-09"}, machine["state"], machine["custody"])
    assert legacy.read_bytes() == b"old" * 21 + b"!"
    assert not (machine["custody"] / "host-backup-gc-09.key").exists()
    assert not any("luksFormat" in c for c in machine["calls"])
    assert any(str(legacy) in c for c in machine["calls"] if "open" in c)


def test_existing_container_without_key_never_generates_a_replacement(
    machine, monkeypatch
):
    machine["world"]["container"] = True
    backup.container("gc-09").touch()
    monkeypatch.setattr(
        backup.os, "urandom", lambda n: pytest.fail("must preserve the missing key")
    )
    with pytest.raises(migration.MigrationError, match="restore its original key"):
        backup.run({"host": "gc-09"}, machine["state"], machine["custody"])
    assert list(machine["custody"].iterdir()) == []
    assert machine["calls"] == []


def test_conflicting_keys_stop_without_changing_either(machine):
    legacy = machine["custody"] / "gc-09" / "host-backup.key"
    legacy.parent.mkdir(mode=0o700)
    legacy.write_bytes(b"a" * 64)
    current = machine["custody"] / "host-backup-gc-09.key"
    current.write_bytes(b"b" * 64)
    with pytest.raises(migration.MigrationError, match="Conflicting backup keys"):
        backup.ensure_key(machine["custody"], "gc-09")
    assert legacy.read_bytes() == b"a" * 64
    assert current.read_bytes() == b"b" * 64


def test_unreadable_backup_location_never_implies_a_missing_container(
    machine, monkeypatch
):
    real_stat = Path.lstat

    def denied(path, *args, **kwargs):
        if path == backup.container("gc-09"):
            raise PermissionError("backup storage is inaccessible")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", denied)
    with pytest.raises(PermissionError, match="inaccessible"):
        backup.ensure_key(machine["custody"], "gc-09")
    assert list(machine["custody"].iterdir()) == []


def test_concurrent_key_creation_reuses_one_credential(machine):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as workers:
        keys = list(
            workers.map(
                lambda _: backup.ensure_key(machine["custody"], "gc-09").read_bytes(),
                range(8),
            )
        )
    assert len(set(keys)) == 1 and len(keys[0]) == 64
