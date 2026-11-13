from __future__ import annotations

import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/provision-identity-salts.py"
MODULE = runpy.run_path(str(SCRIPT))
ACTIVE, LEGACY, MANIFEST = (MODULE[key] for key in ("ACTIVE", "LEGACY", "MANIFEST"))


@pytest.fixture
def stores(tmp_path):
    stores = tuple(tmp_path / name for name in ("deployed", "recovery", "replica"))
    stores[0].mkdir(mode=0o700, exist_ok=True)
    active = stores[0] / ACTIVE
    active.write_bytes(b"a" * 64 + b"\n")
    active.chmod(0o600)
    return stores


def provision(stores):
    MODULE["provision"](*stores, os.getuid(), os.getgid())


def test_fresh_creation_is_private_durable_and_idempotent(stores):
    provision(stores)
    deployed, *backups = stores
    original = (deployed / ACTIVE).read_bytes()
    assert len(original.strip()) == 64
    assert (deployed / LEGACY).read_bytes() == b"default_salt\n"
    manifest = yaml.safe_load((deployed / MANIFEST).read_text())
    assert manifest["active"] == str(deployed / ACTIVE)
    assert manifest["retiring"] == [str(deployed / LEGACY)]
    assert manifest["allow_legacy_default_salt"] is True
    for backup in backups:
        assert (backup / "active.salt").read_bytes() == original
        assert (backup / "active.salt").stat().st_mode & 0o777 == 0o400
        assert backup.stat().st_mode & 0o777 == 0o700
    for name in (ACTIVE, LEGACY, MANIFEST):
        assert (deployed / name).stat().st_mode & 0o777 == 0o600
    provision(stores)
    assert (deployed / ACTIVE).read_bytes() == original


@pytest.mark.parametrize("survivor", [0, 1, 2])
def test_any_surviving_salt_restores_all_missing_copies(stores, survivor):
    provision(stores)
    original = (stores[0] / ACTIVE).read_bytes()
    for index, directory in enumerate(stores):
        if index != survivor:
            for path in directory.iterdir():
                if path.name != ".lock":
                    path.unlink()
    provision(stores)
    assert (stores[0] / ACTIVE).read_bytes() == original
    for directory in stores[1:]:
        assert (directory / "active.salt").read_bytes() == original


def test_adopts_existing_salt_without_rewriting_it(stores):
    stores[0].mkdir(mode=0o700, exist_ok=True)
    active = stores[0] / ACTIVE
    active.write_bytes(b"established-test-salt\r\n")
    active.chmod(0o600)
    provision(stores)
    assert active.read_bytes() == b"established-test-salt\r\n"
    assert (stores[1] / "active.salt").read_bytes() == b"established-test-salt\n"


CENTER = "university_hospital_wuerzburg"
CENTER_FILE = MODULE["CENTER_PREFIX"] + CENTER


def center_source(tmp_path, value=b"c" * 64):
    source = tmp_path / "center-identity"
    source.write_bytes(value + b"\n")
    source.chmod(0o600)
    return source


def provision_center(stores, source, center=CENTER):
    MODULE["provision"](
        *stores, os.getuid(), os.getgid(), source_salt=source, center_id=center
    )


def snapshot(stores):
    return {
        path: path.read_bytes()
        for directory in stores
        if directory.exists()
        for path in directory.iterdir()
        if path.name != ".lock"
    }


def test_shared_center_source_enrolls_two_machines_without_local_generation(
    tmp_path,
):
    source = center_source(tmp_path)
    for prefix in ("first", "second"):
        directories = tuple(
            tmp_path / f"{prefix}-{name}"
            for name in ("deployed", "recovery", "replica")
        )
        provision_center(directories, source)
        deployed = directories[0]
        assert (deployed / CENTER_FILE).read_bytes() == source.read_bytes()
        assert not (deployed / ACTIVE).exists()
        manifest = yaml.safe_load((deployed / MANIFEST).read_text())
        assert manifest == {
            "schema_version": 1,
            "active": str(deployed / CENTER_FILE),
            "retiring": [str(deployed / LEGACY)],
            "allow_legacy_default_salt": True,
            "center_id": CENTER,
            "generation": 1,
        }
        for backup in directories[1:]:
            path = backup / f"center-{CENTER}.salt"
            assert path.read_bytes() == source.read_bytes()
            assert path.stat().st_mode & 0o777 == 0o400


def test_center_enrollment_demotes_established_machine_salt_to_retiring(
    stores, tmp_path
):
    provision(stores)
    deployed = stores[0]
    machine = {
        path: path.read_bytes()
        for path in (
            deployed / ACTIVE,
            stores[1] / "active.salt",
            stores[2] / "active.salt",
            stores[1] / "enrolled",
            stores[2] / "enrolled",
        )
    }
    source = center_source(tmp_path)
    provision_center(stores, source)
    # The machine generation and its recovery evidence are never rewritten.
    assert all(path.read_bytes() == value for path, value in machine.items())
    assert (deployed / CENTER_FILE).read_bytes() == source.read_bytes()
    manifest = yaml.safe_load((deployed / MANIFEST).read_text())
    assert manifest["active"] == str(deployed / CENTER_FILE)
    assert manifest["retiring"] == [str(deployed / ACTIVE), str(deployed / LEGACY)]
    assert (manifest["center_id"], manifest["generation"]) == (CENTER, 1)
    for name in (ACTIVE, LEGACY, MANIFEST, CENTER_FILE):
        assert (deployed / name).stat().st_mode & 0o777 == 0o600
    before = snapshot(stores)
    provision_center(stores, source)
    assert snapshot(stores) == before


def test_center_enrollment_restores_missing_machine_copy_before_switching(
    stores, tmp_path
):
    provision(stores)
    original = (stores[0] / ACTIVE).read_bytes()
    (stores[0] / ACTIVE).unlink()
    provision_center(stores, center_source(tmp_path))
    assert (stores[0] / ACTIVE).read_bytes() == original
    manifest = yaml.safe_load((stores[0] / MANIFEST).read_text())
    assert str(stores[0] / ACTIVE) in manifest["retiring"]


@pytest.mark.parametrize("failure_after", range(1, 6))
def test_interrupted_demotion_keeps_machine_manifest_until_complete(
    stores, tmp_path, monkeypatch, failure_after
):
    provision(stores)
    machine_manifest = (stores[0] / MANIFEST).read_bytes()
    real = MODULE["publish"]
    count = 0

    def interrupted(*args):
        nonlocal count
        real(*args)
        count += 1
        if count == failure_after:
            raise OSError("simulated interruption")

    source = center_source(tmp_path)
    with monkeypatch.context() as patch:
        patch.setitem(
            MODULE["provision"].__globals__, "publish", interrupted
        )
        with pytest.raises(OSError):
            provision_center(stores, source)
    assert (stores[0] / MANIFEST).read_bytes() == machine_manifest
    provision_center(stores, source)
    manifest = yaml.safe_load((stores[0] / MANIFEST).read_text())
    assert manifest["active"] == str(stores[0] / CENTER_FILE)


@pytest.mark.parametrize("change", ["source", "backup"])
def test_an_active_center_salt_wins_and_differing_copies_are_kept(
    stores, tmp_path, change
):
    provision(stores)
    source = center_source(tmp_path)
    provision_center(stores, source)
    original = (stores[0] / CENTER_FILE).read_bytes()
    if change == "source":
        center_source(tmp_path, b"d" * 64)
    else:
        target = stores[1] / f"center-{CENTER}.salt"
        target.chmod(0o600)
        target.write_bytes(b"e" * 64 + b"\n")
    provision_center(stores, source)
    assert (stores[0] / CENTER_FILE).read_bytes() == original
    if change == "backup":
        assert (stores[1] / f"center-{CENTER}.salt").read_bytes() == original
        kept = list(stores[1].glob(f"center-{CENTER}.salt.superseded-*"))
        assert kept[0].read_bytes() == b"e" * 64 + b"\n"


def test_an_active_center_is_kept_when_another_is_configured(stores, tmp_path):
    provision(stores)
    provision_center(stores, center_source(tmp_path))
    before = snapshot(stores)
    provision_center(stores, center_source(tmp_path), center="rbk_stuttgart")
    assert snapshot(stores) == before


def test_an_active_center_is_kept_when_the_inventory_leaves_it(stores, tmp_path):
    provision(stores)
    provision_center(stores, center_source(tmp_path))
    before = snapshot(stores)
    provision(stores)
    assert snapshot(stores) == before


def test_a_lost_machine_salt_does_not_stop_a_center_host(stores, tmp_path):
    provision(stores)
    provision_center(stores, center_source(tmp_path))
    for directory in stores:
        for name in (ACTIVE, "active.salt"):
            if (directory / name).exists():
                (directory / name).unlink()
    provision_center(stores, center_source(tmp_path))
    manifest = yaml.safe_load((stores[0] / MANIFEST).read_text())
    assert str(stores[0] / ACTIVE) not in manifest["retiring"]
    assert (stores[0] / CENTER_FILE).exists()
    assert list(stores[1].glob("enrolled.superseded-*"))


@pytest.mark.parametrize("kind", ["missing", "public", "symlink", "default"])
def test_center_source_failure_keeps_the_machine_salt_and_continues(
    stores, tmp_path, kind
):
    provision(stores)
    before = snapshot(stores)
    source = tmp_path / "center-identity"
    if kind == "symlink":
        source.symlink_to(stores[0] / ACTIVE)
    elif kind != "missing":
        source.write_bytes(
            b"default_salt\n" if kind == "default" else b"c" * 64 + b"\n"
        )
        source.chmod(0o644 if kind == "public" else 0o600)
    provision_center(stores, source)
    assert snapshot(stores) == before


@pytest.mark.parametrize("center", ["", "../x", "a/b", "-lead", "x" * 129])
def test_unsafe_center_keys_are_rejected(stores, tmp_path, center):
    with pytest.raises(ValueError, match="center"):
        provision_center(stores, center_source(tmp_path), center=center)


def test_a_center_salt_delivered_later_enrolls_over_the_host_salt(stores, tmp_path):
    missing = tmp_path / "center-identity"
    provision_center(stores, missing)
    assert (stores[0] / ACTIVE).read_bytes() == b"a" * 64 + b"\n"
    assert not (stores[0] / CENTER_FILE).exists()
    provision_center(stores, center_source(tmp_path))
    manifest = yaml.safe_load((stores[0] / MANIFEST).read_text())
    assert manifest["active"] == str(stores[0] / CENTER_FILE)
    assert str(stores[0] / ACTIVE) in manifest["retiring"]


def test_cli_requires_center_for_source_salt(stores, tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--secret-dir",
            str(stores[0]),
            "--recovery-dir",
            str(stores[1]),
            "--replica-dir",
            str(stores[2]),
            "--user",
            "root",
            "--group",
            "root",
            "--source-salt",
            str(center_source(tmp_path)),
        ],
        capture_output=True,
    )
    assert result.returncode == 1
    assert b"c" * 64 not in result.stdout + result.stderr


@pytest.mark.parametrize("evidence", ["manifest", "receipt", "legacy"])
def test_a_host_left_with_only_traces_gets_a_new_salt(stores, evidence):
    provision(stores)
    keep = {"manifest": MANIFEST, "receipt": "enrolled", "legacy": LEGACY}[evidence]
    for directory in stores:
        for path in directory.iterdir():
            if path.name not in {keep, ".lock"}:
                path.unlink()
    provision(stores)
    created = (stores[0] / ACTIVE).read_bytes().strip()
    assert len(created) == 64 and created != b"a" * 64
    assert (stores[0] / LEGACY).read_bytes() == b"default_salt\n"
    if evidence == "receipt":
        assert list(stores[1].glob("enrolled.superseded-*"))
    provision(stores)
    assert (stores[0] / ACTIVE).read_bytes().strip() == created


def test_a_host_that_used_default_salt_gets_a_real_one_and_can_still_read_it(stores):
    (stores[0] / ACTIVE).write_bytes(b"default_salt\n")
    provision(stores)
    created = (stores[0] / ACTIVE).read_bytes().strip()
    assert len(created) == 64
    manifest = yaml.safe_load((stores[0] / MANIFEST).read_text())
    assert manifest["allow_legacy_default_salt"] is True
    assert str(stores[0] / LEGACY) in manifest["retiring"]
    assert list(stores[0].glob(f"{ACTIVE}.superseded-*"))


@pytest.mark.parametrize("index", [0, 1, 2])
def test_conflicting_copies_resolve_to_the_receipted_salt_and_are_kept(stores, index):
    provision(stores)
    original = (stores[0] / ACTIVE).read_bytes()
    name = ACTIVE if index == 0 else "active.salt"
    target = stores[index] / name
    target.chmod(0o600)
    target.write_bytes(b"different-test-salt\n")
    provision(stores)
    assert (stores[0] / ACTIVE).read_bytes() == original
    assert (stores[1] / "active.salt").read_bytes() == original
    assert (stores[2] / "active.salt").read_bytes() == original
    kept = list(stores[index].glob(f"{name}.superseded-*"))
    assert kept[0].read_bytes() == b"different-test-salt\n"


@pytest.mark.parametrize("failure_after", range(1, 7))
def test_interrupted_publication_resumes_same_salt(stores, monkeypatch, failure_after):
    real = MODULE["publish"]
    count = 0

    def interrupted(*args):
        nonlocal count
        real(*args)
        count += 1
        if count == failure_after:
            raise OSError("simulated interruption")

    with monkeypatch.context() as patch:
        patch.setitem(MODULE["provision"].__globals__, "publish", interrupted)
        with pytest.raises(OSError):
            provision(stores)
    original = (stores[1] / "active.salt").read_bytes()
    provision(stores)
    assert (stores[0] / ACTIVE).read_bytes() == original


@pytest.mark.parametrize("kind", ["symlink", "empty", "public", "receipt", "manifest"])
def test_unusable_files_are_set_aside_and_the_salt_survives(stores, kind):
    provision(stores)
    original = (stores[1] / "active.salt").read_bytes()
    active = stores[0] / ACTIVE
    if kind == "symlink":
        active.unlink()
        active.symlink_to(stores[1] / "active.salt")
    elif kind == "empty":
        active.write_bytes(b"")
    elif kind == "public":
        active.chmod(0o644)
    elif kind == "receipt":
        receipt = stores[1] / "enrolled"
        receipt.chmod(0o600)
        receipt.write_bytes(b"incorrect\n")
    else:
        (stores[0] / MANIFEST).write_text("active: /different/generation\n")
    provision(stores)
    assert (stores[0] / ACTIVE).read_bytes() == original
    assert not (stores[0] / ACTIVE).is_symlink()
    assert (stores[0] / ACTIVE).stat().st_mode & 0o077 == 0
    manifest = yaml.safe_load((stores[0] / MANIFEST).read_text())
    assert manifest["active"] == str(stores[0] / ACTIVE)


def test_cli_requires_authoritative_source_and_encrypted_storage(stores):
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True)
    assert result.returncode == 2


def test_a_new_host_creates_its_own_random_salt(tmp_path):
    stores = tuple(tmp_path / name for name in ("deployed", "recovery", "replica"))
    provision(stores)
    first = (stores[0] / ACTIVE).read_bytes().strip()
    assert len(first) == 64
    provision(stores)
    assert (stores[0] / ACTIVE).read_bytes().strip() == first
