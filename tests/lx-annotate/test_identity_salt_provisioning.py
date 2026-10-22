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


def test_shared_center_source_enrolls_two_machines_without_local_generation(
    stores, tmp_path
):
    source = tmp_path / "center-identity"
    source.write_bytes(b"a" * 64 + b"\n")
    source.chmod(0o600)
    other = tuple(
        tmp_path / f"second-{name}" for name in ("deployed", "recovery", "replica")
    )
    for directories in (stores, other):
        MODULE["provision"](*directories, os.getuid(), os.getgid(), source)
        assert (directories[0] / ACTIVE).read_bytes() == source.read_bytes()


@pytest.mark.parametrize("kind", ["missing", "public", "symlink", "different"])
def test_center_source_failure_never_replaces_established_machine_salt(
    stores, tmp_path, kind
):
    provision(stores)
    before = (stores[0] / ACTIVE).read_bytes()
    source = tmp_path / "center-identity"
    if kind == "symlink":
        source.symlink_to(stores[0] / ACTIVE)
    elif kind != "missing":
        source.write_bytes(
            b"different-center-material\n" if kind == "different" else before
        )
        source.chmod(0o644 if kind == "public" else 0o600)
    with pytest.raises((ValueError, OSError)):
        MODULE["provision"](*stores, os.getuid(), os.getgid(), source)
    assert (stores[0] / ACTIVE).read_bytes() == before


def test_missing_center_source_never_generates_a_machine_identity(stores, tmp_path):
    with pytest.raises(ValueError, match="unavailable"):
        MODULE["provision"](*stores, os.getuid(), os.getgid(), tmp_path / "missing")
    assert (stores[0] / ACTIVE).read_bytes() == b"a" * 64 + b"\n"


@pytest.mark.parametrize("evidence", ["manifest", "receipt", "legacy"])
def test_never_regenerates_if_only_enrollment_evidence_survives(stores, evidence):
    provision(stores)
    keep = {"manifest": MANIFEST, "receipt": "enrolled", "legacy": LEGACY}[evidence]
    for directory in stores:
        for path in directory.iterdir():
            if path.name not in {keep, ".lock"}:
                path.unlink()
    with pytest.raises(ValueError, match="Previously enrolled"):
        provision(stores)
    assert not (stores[0] / ACTIVE).exists()


@pytest.mark.parametrize("index", [0, 1, 2])
def test_conflicting_copies_are_preserved(stores, index):
    provision(stores)
    target = stores[index] / (ACTIVE if index == 0 else "active.salt")
    target.chmod(0o600)
    target.write_bytes(b"different-test-salt\n")
    before = {
        path: path.read_bytes()
        for directory in stores
        for path in directory.iterdir()
        if path.name != ".lock"
    }
    with pytest.raises(ValueError, match="disagree"):
        provision(stores)
    assert all(path.read_bytes() == value for path, value in before.items())


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
def test_unsafe_or_corrupt_inputs_fail_closed(stores, kind):
    provision(stores)
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
    with pytest.raises((ValueError, OSError)):
        provision(stores)


def test_cli_requires_authoritative_source_and_encrypted_storage(stores):
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True)
    assert result.returncode == 2


def test_missing_authoritative_salt_never_generates_locally(tmp_path):
    stores = tuple(tmp_path / name for name in ("deployed", "recovery", "replica"))
    with pytest.raises(ValueError, match="local generation is prohibited"):
        provision(stores)
