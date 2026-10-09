from __future__ import annotations

import grp
import os
from pathlib import Path
import pwd
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
    return tuple(tmp_path / name for name in ("deployed", "recovery", "replica"))


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
    stores[0].mkdir(mode=0o700)
    active = stores[0] / ACTIVE
    active.write_bytes(b"established-test-salt\r\n")
    active.chmod(0o600)
    provision(stores)
    assert active.read_bytes() == b"established-test-salt\r\n"
    assert (stores[1] / "active.salt").read_bytes() == b"established-test-salt\n"


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


@pytest.mark.parametrize("failure_after", range(1, 8))
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
    if failure_after < 5:
        assert not (stores[0] / ACTIVE).exists()
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


def test_concurrent_cli_runs_share_one_salt_and_do_not_log_it(stores):
    command = [sys.executable, str(SCRIPT)]
    for option, directory in zip(("secret-dir", "recovery-dir", "replica-dir"), stores):
        command.extend([f"--{option}", str(directory)])
    command.extend(
        [
            "--user",
            pwd.getpwuid(os.getuid()).pw_name,
            "--group",
            grp.getgrgid(os.getgid()).gr_name,
        ]
    )
    processes = [
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(4)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        assert (stores[0] / ACTIVE).read_bytes().strip() not in stdout + stderr
    provision(stores)
