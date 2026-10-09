import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace
from types import ModuleType

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts/storage/mount_persisting_storage.py"
)


def _entrypoint() -> ModuleType:
    spec = importlib.util.spec_from_file_location("luxnix_mount_entrypoint", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entrypoint_skips_mount_when_not_required(monkeypatch, capsys):
    namespace = _entrypoint()
    storage = SimpleNamespace(storage_persisting_mount_point=Path("/unused"))
    monkeypatch.setattr(
        namespace, "initialize_storage_manager_from_env", lambda: storage
    )
    monkeypatch.setattr(namespace, "external_drive_requires_mount", lambda _sm: False)

    assert namespace.main() == 0
    assert "already mounted or not required" in capsys.readouterr().out


def test_entrypoint_requires_the_configured_device(monkeypatch):
    namespace = _entrypoint()
    storage = SimpleNamespace(storage_persisting_mount_point=Path("/mnt/data"))
    monkeypatch.setattr(
        namespace, "initialize_storage_manager_from_env", lambda: storage
    )
    monkeypatch.setattr(namespace, "external_drive_requires_mount", lambda _sm: True)
    monkeypatch.setattr(namespace, "drive_with_serial_available", lambda _sm: None)

    with pytest.raises(RuntimeError, match="configured serial is not available"):
        namespace.main()


def test_entrypoint_redacts_mount_process_output(monkeypatch):
    namespace = _entrypoint()
    storage = SimpleNamespace(storage_persisting_mount_point=Path("/mnt/data"))
    monkeypatch.setattr(
        namespace, "initialize_storage_manager_from_env", lambda: storage
    )
    monkeypatch.setattr(namespace, "external_drive_requires_mount", lambda _sm: True)
    monkeypatch.setattr(
        namespace, "drive_with_serial_available", lambda _sm: Path("/dev/test")
    )

    def fail_mount(*args, **kwargs):
        raise subprocess.CalledProcessError(
            32,
            ["mount"],
            output="TOP_SECRET_STDOUT",
            stderr="TOP_SECRET_STDERR",
        )

    monkeypatch.setattr(namespace, "mount_drive", fail_mount)

    with pytest.raises(RuntimeError, match=r"mount failed \(exit 32\)") as error:
        namespace.main()

    assert "TOP_SECRET_STDOUT" not in str(error.value)
    assert "TOP_SECRET_STDERR" not in str(error.value)
