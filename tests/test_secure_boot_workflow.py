"""Fail-closed signing completion; no firmware or remote operations."""
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from lx_administration import secure_boot as boot


def test_changed_generation_never_activates(monkeypatch):
    monkeypatch.setattr(boot, "host_generation", lambda _: (8, "/nix/store/new"))
    calls = []
    monkeypatch.setattr(boot.subprocess, "run", lambda *a, **k: calls.append(a))
    with pytest.raises(boot.SecureBootError, match="generation changed"):
        boot.finish_generation(["host"], 7, "/nix/store/reviewed", "switch")
    assert calls == []


@pytest.mark.parametrize("action", ["boot", "switch"])
def test_finish_reuses_exact_closure_without_reboot(monkeypatch, action):
    system = "/nix/store/reviewed"
    monkeypatch.setattr(boot, "host_generation", lambda _: (7, system))
    monkeypatch.setattr(boot, "run", lambda *a, **k: '{"status":"awaiting-ack"}' if 'status' in a else system)
    calls = []
    def execute(*a, **k):
        calls.append(a[0])
        return SimpleNamespace(stdout='a' * 24)
    monkeypatch.setattr(boot.subprocess, "run", execute)
    boot.finish_generation(["host"], 7, system, action)
    boot.finish_generation(["host"], 7, system, action)
    assert sum(any(' start ' in arg for arg in c) for c in calls) == 2
    assert sum('ack' in c for c in calls) == 2
    assert not any('reboot' in c or 'test' in c for c in calls)


def test_failed_switch_or_wrong_active_system_is_not_success(monkeypatch):
    monkeypatch.setattr(boot, "host_generation", lambda _: (7, "/nix/store/reviewed"))
    monkeypatch.setattr(boot.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout='a' * 24))
    monkeypatch.setattr(boot, "run", lambda *a, **k: '{"status":"awaiting-ack"}' if 'status' in a else "/nix/store/old")
    with pytest.raises(boot.SecureBootError, match="Activation did not"):
        boot.finish_generation(["host"], 7, "/nix/store/reviewed", "switch")


def test_source_refuses_temporary_dirty_or_foreign_inventory(monkeypatch):
    with pytest.raises(boot.SecureBootError, match="durable"):
        boot.reviewed_source(Path("/tmp/release"), Path("/tmp/release/ansible/inventory/hosts.ini"))
    checkout = Path("/home/release")
    with pytest.raises(boot.SecureBootError, match="canonical inventory"):
        boot.reviewed_source(checkout, Path("/home/other/hosts.ini"))
    monkeypatch.setattr(boot, "run", lambda *a: " M changed")
    with pytest.raises(boot.SecureBootError, match="commit"):
        boot.reviewed_source(checkout, checkout / "ansible/inventory/hosts.ini")


def test_immutable_conflict_cannot_partially_replace_bootloader(tmp_path, monkeypatch):
    esp = tmp_path / "esp"
    loader = "EFI/BOOT/BOOTX64.EFI"
    stub = "EFI/Linux/nixos-generation-7-abc.efi"
    for name in (loader, stub):
        target = esp / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"old")
    archive = tmp_path / "boot.tar"
    with tarfile.open(archive, "w") as tar:
        for name in (loader, stub):
            info = tarfile.TarInfo(name)
            info.size = 3
            tar.addfile(info, io.BytesIO(b"new"))
    monkeypatch.setattr(boot, "_tool", lambda _: "sbverify")
    monkeypatch.setattr(boot, "run", lambda *a, **k: "")
    with pytest.raises(boot.SecureBootError, match="immutable"):
        boot.import_artifacts(archive, esp, tmp_path / "certificate")
    assert (esp / loader).read_bytes() == b"old"
    assert (esp / stub).read_bytes() == b"old"


def test_concurrent_import_refused_before_verification(tmp_path, monkeypatch):
    import fcntl
    import os
    esp = tmp_path / "esp"
    esp.mkdir()
    fd = os.open(esp, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            boot.import_artifacts(tmp_path / "absent", esp, tmp_path / "cert")
    finally:
        os.close(fd)


def test_cancelled_signing_never_opens_custody_or_delivers(tmp_path, monkeypatch):
    public = tmp_path / "conf/secure-boot"
    public.mkdir(parents=True)
    (public / "db.pem").write_bytes(b"test-public-certificate")
    monkeypatch.setattr(boot, "_require_tty", lambda: None)
    monkeypatch.setattr(boot, "reviewed_source", lambda *a: "reviewed-revision")
    monkeypatch.setattr(boot, "_nix", lambda *a, **k: "true")
    monkeypatch.setattr(boot, "_ssh_target", lambda *a: ["gc-09"])
    monkeypatch.setattr(boot, "host_generation", lambda *a: (7, "/nix/store/reviewed"))
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        if args[-1] == "hostname":
            return "gc-09"
        return "/nix/store/reviewed"
    monkeypatch.setattr(boot, "run", run)
    monkeypatch.setattr("builtins.input", lambda _: "cancel")
    monkeypatch.setattr(boot, "private_workspace", lambda: pytest.fail("custody opened after cancellation"))
    with pytest.raises(boot.SecureBootError, match="Cancelled"):
        boot.sign_host("gc-09", tmp_path, tmp_path / "custody", tmp_path / "inventory", "boot")
    assert not any(args[0] == "scp" or "import" in args for args in calls)


def test_firmware_database_requires_exact_certificate_and_valid_lengths():
    import struct
    certificate = b'public-der-certificate'
    entry = b'0' * 16 + certificate
    database = boot.X509_GUID + struct.pack('<III', 28 + len(entry), 0, len(entry)) + entry
    assert boot.enrolled_certificate(database, certificate)
    assert not boot.enrolled_certificate(database, b'other-certificate')
    with pytest.raises(boot.SecureBootError, match='Malformed'):
        boot.enrolled_certificate(database[:-1], certificate)


def test_wrong_firmware_signer_prevents_detached_activation(monkeypatch):
    monkeypatch.setattr(boot, 'host_generation', lambda _: (7, '/nix/store/reviewed'))
    calls = []
    def fail(*a, **k):
        calls.append(a[0])
        raise boot.subprocess.CalledProcessError(1, a[0])
    monkeypatch.setattr(boot.subprocess, 'run', fail)
    with pytest.raises(boot.subprocess.CalledProcessError):
        boot.finish_generation(['host'], 7, '/nix/store/reviewed', 'boot')
    assert len(calls) == 1 and calls[0][-1] == 'verify-firmware'
