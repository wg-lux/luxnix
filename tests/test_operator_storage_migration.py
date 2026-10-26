"""Exercise real rsync copies on disposable files; never open or format a device."""
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from lx_administration.storage import operator_migration as migration


@pytest.fixture
def layout(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    volume = tmp_path / "encrypted"
    volume.mkdir()
    config = {"volumes": {"data": {"mountPoint": str(volume)}},
              "binds": {str(source): {"volume": "data", "directory": "data"}}, "writers": ["consumer"]}
    original = migration.run
    def run(*args, **kwargs):
        if args[0] == "systemctl":
            return b"0\n"
        if args[0] == "findmnt":
            return b"test-filesystem-uuid\n"
        return original(*args, **kwargs)
    monkeypatch.setattr(migration, "run", run)
    monkeypatch.setattr(migration.os.path, "ismount", lambda path: path == volume)
    verifier = SimpleNamespace(encrypted_storage=lambda path: None)
    return source, volume, migration.Migration(config, verifier)


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync required")
def test_copy_verifies_metadata_hardlinks_and_does_not_recopy_stale_source(layout):
    source, volume, task = layout
    (source / "record").write_bytes(b"original data")
    (source / "record").chmod(0o600)
    os.link(source / "record", source / "linked")
    task.prepare()
    destination = volume / "data"
    assert (destination / "record").read_bytes() == b"original data"
    assert (destination / "record").stat().st_mode & 0o777 == 0o600
    assert (destination / "record").stat().st_ino == (destination / "linked").stat().st_ino
    assert (source / "record").exists()
    (destination / "record").write_bytes(b"new application data")
    task.prepare()
    assert (destination / "record").read_bytes() == b"new application data"


def test_unencrypted_target_is_rejected_before_copy(layout):
    source, volume, task = layout
    def reject(path):
        raise ValueError("unencrypted")
    task.verifier.encrypted_storage = reject
    with pytest.raises(ValueError):
        task.prepare()
    assert list(volume.iterdir()) == []


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync required")
def test_conflicting_populated_destination_is_never_overwritten(layout):
    source, volume, task = layout
    (source / "record").write_text("source")
    (volume / "data").mkdir()
    (volume / "data" / "record").write_text("existing encrypted data")
    with pytest.raises(migration.MigrationError, match="refusing overwrite"):
        task.prepare()
    assert (volume / "data" / "record").read_text() == "existing encrypted data"


def test_running_writer_is_not_stopped_or_copied(layout, monkeypatch):
    source, volume, task = layout
    original = migration.run
    monkeypatch.setattr(migration, "run", lambda *args, **kwargs: b"123\n" if args[0] == "systemctl" else original(*args, **kwargs))
    with pytest.raises(migration.MigrationError, match="writer is running"):
        task.prepare()
    assert not (volume / "data").exists()


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync required")
def test_interrupted_private_copy_resumes_and_verifies(layout, monkeypatch):
    source, volume, task = layout
    (source / "record").write_text("preserved source")
    original = task.copy
    monkeypatch.setattr(task, "copy", lambda *args, **kwargs: (_ for _ in ()).throw(migration.MigrationError("interrupted")))
    with pytest.raises(migration.MigrationError):
        task.prepare()
    assert (volume / "data.luxnix-copy" / "plan.json").exists()
    monkeypatch.setattr(task, "copy", original)
    task.prepare()
    assert (volume / "data" / "record").read_text() == "preserved source"
    assert not (volume / "data.luxnix-copy").exists()


def test_existing_container_is_never_formatted(tmp_path, monkeypatch):
    container = tmp_path / "already-populated.luks"
    container.write_bytes(b"existing content must not be overwritten")
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        if args[:2] == ("cryptsetup", "isLuks"):
            raise migration.MigrationError("not LUKS")
        raise AssertionError(args)
    monkeypatch.setattr(migration, "run", run)
    task = migration.Migration({"volumes": {"data": {"container": str(container), "device": "/dev/mapper/test-never-created"}}},
                               SimpleNamespace(_require_protected_swap=lambda: None))
    with pytest.raises(migration.MigrationError):
        task.unlock("data")
    assert calls == [("cryptsetup", "isLuks", str(container))]
    assert container.read_bytes() == b"existing content must not be overwritten"


def test_account_hash_copy_preserves_bytes_and_existing_rotations(tmp_path):
    source, target = tmp_path / "source", tmp_path / "boot" / "account.hash"
    source.write_bytes(b"existing account hash\n")
    source.chmod(0o600)
    migration.prepare_accounts({str(target): str(source)})
    assert target.read_bytes() == source.read_bytes()
    assert target.stat().st_mode & 0o777 == 0o600
    target.write_bytes(b"subsequent rotation\n")
    migration.prepare_accounts({str(target): str(source)})
    assert target.read_bytes() == b"subsequent rotation\n"


def test_new_container_uses_private_prompts_and_only_formats_exclusive_file(tmp_path, monkeypatch):
    container = tmp_path / "new.luks"
    calls = []
    def run(*args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "systemd-ask-password":
            return b"temporary VM test passphrase\n"
        assert container.exists()
        return b""
    monkeypatch.setattr(migration, "run", run)
    monkeypatch.setattr(migration.os, "posix_fallocate", lambda fd, offset, size: os.ftruncate(fd, size))
    task = migration.Migration({"volumes": {"data": {"container": str(container), "device": "/dev/mapper/test-never-created", "minimumSizeMiB": 1}}, "binds": {}},
                               SimpleNamespace(_require_protected_swap=lambda: None))
    task.unlock("data")
    assert container.stat().st_mode & 0o777 == 0o600
    assert [args[0] for args, _ in calls] == ["systemd-ask-password", "systemd-ask-password", "cryptsetup", "cryptsetup", "mkfs.ext4"]
    for args, kwargs in calls:
        assert not any("temporary VM test passphrase" in arg for arg in args)
    assert list(tmp_path.iterdir()) == [container]


def test_mismatched_new_passphrase_does_not_create_storage(tmp_path, monkeypatch):
    container = tmp_path / "new.luks"
    prompts = iter([b"one\n", b"different\n"])
    monkeypatch.setattr(migration, "run", lambda *args, **kwargs: next(prompts))
    task = migration.Migration({"volumes": {"data": {"container": str(container), "device": "/dev/mapper/test-never-created", "minimumSizeMiB": 1}}, "binds": {}},
                               SimpleNamespace(_require_protected_swap=lambda: None))
    with pytest.raises(migration.MigrationError, match="do not match"):
        task.unlock("data")
    assert not container.exists()
