"""Fault tests for the writer boundary and physical backup destinations."""

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from lx_administration import secret_storage

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "hub_backup",
    ROOT / "modules/nixos/services/lx-annotate-local/scripts/hub-backup.py",
)
backup = importlib.util.module_from_spec(spec)
previous = sys.modules.get("secret_storage")
sys.modules["secret_storage"] = secret_storage
spec.loader.exec_module(backup)
if previous is None:
    del sys.modules["secret_storage"]
else:
    sys.modules["secret_storage"] = previous


@pytest.fixture
def configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "encrypted_storage", lambda path: None)
    root = tmp_path / "data"
    root.mkdir()
    return {
        "protected_root": str(root),
        "source": str(root),
        "destinations": [
            str(root / name) for name in ["incoming", "custom", "manifests"]
        ],
        "writers": ["web.service", "worker.service", "worker.timer"],
        "capture_command": ["capture"],
    }


def test_custom_destinations_get_mandatory_exclusions(configuration):
    assert backup.validate_paths(configuration) == [
        "/incoming/",
        "/custom/",
        "/manifests/",
    ]


@pytest.mark.parametrize(
    "fault", ["traversal", "symlink", "outside", "overlap", "source"]
)
def test_invalid_destination_fails_before_capture(configuration, tmp_path, fault):
    root = Path(configuration["source"])
    destinations = configuration["destinations"]
    if fault == "traversal":
        destinations[0] = str(root / ".." / "escape")
    elif fault == "symlink":
        (root / "link").symlink_to(tmp_path, target_is_directory=True)
        destinations[0] = str(root / "link" / "escape")
    elif fault == "outside":
        destinations[0] = str(tmp_path / "escape")
    elif fault == "overlap":
        destinations[0] = destinations[1] + "/nested"
    else:
        destinations[0] = str(root)
    with pytest.raises(ValueError):
        backup.validate_paths(configuration)
    assert not (root / "custom").exists()


@pytest.mark.parametrize("failure", [None, "stop", "capture", "unclean"])
def test_same_writer_pause_covers_dump_and_media_and_recovers(
    configuration, tmp_path, monkeypatch, failure
):
    active = {"web.service", "worker.timer"}
    original = set(active)
    captures = []
    failed = False

    def run(*args, **kwargs):
        nonlocal failed
        command = args[0] if args[0] == "capture" else args[1]
        if failure == command and not failed:
            failed = True
            raise RuntimeError("synthetic interruption")
        if command == "show":
            if "--property=Result" in args:
                return "timeout" if failure == "unclean" else "success"
            unit = args[2]
            state = "active" if unit in active else "inactive"
            if args[-1] == "--value":
                return state
            return f"LoadState=loaded\nActiveState={state}\nUnitFileState=enabled"
        if command == "stop":
            active.difference_update(args[2:])
        elif command == "start":
            assert not (tmp_path / "quiescing").exists()
            active.add(args[-1])
        elif command == "capture":
            assert not active
            assert (tmp_path / "quiescing").exists()
            assert json.loads(args[1]) == ["/incoming/", "/custom/", "/manifests/"]
            captures.append("fresh dump and media")
        return ""

    monkeypatch.setattr(backup, "run", run)
    journal = tmp_path / "recovery.json"
    if failure:
        with pytest.raises((RuntimeError, ValueError)):
            backup.capture(configuration, journal)
    else:
        backup.capture(configuration, journal)
        assert captures == ["fresh dump and media"]
    assert active == original and not (tmp_path / "quiescing").exists()
    assert not journal.exists()


def test_failed_restart_retains_recoverable_journal(
    configuration, tmp_path, monkeypatch
):
    journal = tmp_path / "recovery.json"
    backup.save(journal, {"active": ["web.service"]})
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        if args[1] == "start":
            raise RuntimeError("restart failed")
        return ""

    monkeypatch.setattr(backup, "run", run)
    with pytest.raises(RuntimeError):
        backup.recover(configuration, journal)
    assert json.loads(journal.read_text()) == {"active": ["web.service"]}
    monkeypatch.setattr(backup, "run", lambda *a, **k: "")
    backup.recover(configuration, journal)
    assert not journal.exists()


def test_encryption_failure_stops_before_unit_mutation(
    configuration, tmp_path, monkeypatch
):
    def reject(path):
        raise ValueError("plaintext backing")

    monkeypatch.setattr(backup, "encrypted_storage", reject)
    monkeypatch.setattr(backup, "run", lambda *a, **k: pytest.fail("unit mutation"))
    with pytest.raises(ValueError, match="plaintext"):
        backup.capture(configuration, tmp_path / "recovery.json")
