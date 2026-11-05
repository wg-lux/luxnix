"""Real disposable LUKS keyslots; host mounts and interactive input are isolated."""

import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import termios

import pytest

from lx_administration.storage import boot_password as setup

OLD = b"synthetic-existing-recovery-password"
NEW = b"synthetic-new-operator-password"


@pytest.fixture
def disk(tmp_path, monkeypatch):
    image = tmp_path / "disposable.luks"
    with image.open("wb") as stream:
        stream.truncate(32 * 1024 * 1024)
    with setup.key_fd(OLD) as fd:
        result = setup.cryptsetup(
            "luksFormat",
            "--type",
            "luks2",
            "--batch-mode",
            "--pbkdf",
            "pbkdf2",
            "--pbkdf-force-iterations",
            "1000",
            "--key-file",
            f"/proc/self/fd/{fd}",
            str(image),
            pass_fds=(fd,),
        )
    assert result.returncode == 0
    machine = tmp_path / "machine-id"
    machine.write_text("1" * 32)
    monkeypatch.setattr(setup, "MACHINE_ID", machine)
    monkeypatch.setattr(setup, "STATE", tmp_path / "state")
    monkeypatch.setattr(setup.boot, "verify_mount", lambda *args: None)
    monkeypatch.setattr(setup.boot, "encrypted_storage", lambda *args: None)
    uuid = setup.cryptsetup("luksUUID", str(image)).stdout.decode().strip()
    monkeypatch.setattr(setup.boot, "key_device", lambda *args: (uuid, 1, 2))
    return str(image)


def answers(monkeypatch, *values):
    pending = iter(values)
    monkeypatch.setattr(setup, "secret", lambda prompt: next(pending))


def test_existing_password_proof_is_private_and_reused_without_prompt(
    disk, monkeypatch
):
    before = setup.header_digest(disk)
    answers(monkeypatch, OLD, OLD)
    setup.prepare(disk)
    receipt = setup.STATE / "cryptroot.json"
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert OLD not in receipt.read_bytes()
    assert setup.header_digest(disk) == before
    assert not list(setup.STATE.glob("header-before-*"))
    monkeypatch.setattr(
        setup, "secret", lambda prompt: pytest.fail("unexpected prompt")
    )
    setup.prepare(disk)
    assert setup.header_digest(disk) == before


def test_addition_verifies_new_and_recovery_and_backs_up_before_change(
    disk, monkeypatch
):
    original = Path(disk).read_bytes()[: 16 * 1024 * 1024]
    before = json.loads(
        setup.cryptsetup("luksDump", "--dump-json-metadata", disk).stdout
    )
    answers(monkeypatch, NEW, NEW, OLD)
    setup.prepare(disk, change=True)
    assert setup.accepts(disk, NEW) and setup.accepts(disk, OLD)
    after = json.loads(
        setup.cryptsetup("luksDump", "--dump-json-metadata", disk).stdout
    )
    assert after["keyslots"]["0"] == before["keyslots"]["0"]
    assert len(after["keyslots"]) == len(before["keyslots"]) + 1
    (backup,) = setup.STATE.glob("header-before-*/luks.header")
    assert backup.read_bytes() == original
    assert backup.stat().st_mode & 0o777 == 0o600
    record = (setup.STATE / "cryptroot.json").read_bytes()
    assert OLD not in record and NEW not in record


@pytest.mark.parametrize("values", [(NEW, OLD), (NEW, NEW, b"wrong-recovery")])
def test_mismatch_and_wrong_authorization_never_modify_header(
    disk, monkeypatch, values
):
    before = setup.header_digest(disk)
    answers(monkeypatch, *values)
    with pytest.raises(ValueError):
        setup.prepare(disk, change=True)
    assert setup.header_digest(disk) == before
    assert not (setup.STATE / "cryptroot.json").exists()
    assert not list(setup.STATE.glob("header-before-*"))


@pytest.mark.parametrize("change", ["header", "machine", "explicit"])
def test_changed_identity_header_or_explicit_change_requires_prompt(
    disk, monkeypatch, change
):
    answers(monkeypatch, OLD, OLD)
    setup.prepare(disk)
    if change == "header":
        assert (
            setup.cryptsetup("config", "--label", "synthetic-change", disk).returncode
            == 0
        )
    elif change == "machine":
        setup.MACHINE_ID.write_text("2" * 32)
    answers(monkeypatch)  # An exhausted input iterator proves a prompt was attempted.
    with pytest.raises(StopIteration):
        setup.prepare(disk, change=change == "explicit")


def test_wrong_mapping_is_rejected_before_prompt(disk, monkeypatch):
    def wrong(*args):
        raise ValueError("wrong mapping")

    monkeypatch.setattr(setup.boot, "key_device", wrong)
    monkeypatch.setattr(
        setup, "secret", lambda prompt: pytest.fail("prompt on wrong disk")
    )
    with pytest.raises(ValueError, match="wrong mapping"):
        setup.prepare(disk)


def test_mapping_change_during_prompt_does_not_enroll(disk, monkeypatch):
    before = setup.header_digest(disk)
    values = iter([("same-uuid", 1, 2), ("same-uuid", 3, 4)])
    monkeypatch.setattr(setup.boot, "key_device", lambda *args: next(values))
    answers(monkeypatch, NEW, NEW, OLD)
    with pytest.raises(ValueError, match="identity or keyslots changed"):
        setup.prepare(disk, change=True)
    assert setup.header_digest(disk) == before
    assert not (setup.STATE / "cryptroot.json").exists()


@pytest.mark.parametrize("unsafe", ["permissions", "symlink"])
def test_unsafe_receipt_is_rejected(disk, monkeypatch, unsafe):
    answers(monkeypatch, OLD, OLD)
    setup.prepare(disk)
    receipt = setup.STATE / "cryptroot.json"
    if unsafe == "permissions":
        receipt.chmod(0o644)
    else:
        saved = setup.STATE / "saved.json"
        receipt.rename(saved)
        receipt.symlink_to(saved)
    with pytest.raises(ValueError, match="private"):
        setup.prepare(disk)


def test_no_terminal_never_falls_back_to_echoed_stdin():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from lx_administration.storage.boot_password import secret; "
            "secret('private prompt: ')",
        ],
        input=NEW + b"\n",
        capture_output=True,
        start_new_session=True,
        check=False,
    )
    assert result.returncode != 0
    assert NEW not in result.stdout + result.stderr
    assert b"Password input may be echoed" not in result.stderr


def test_real_terminal_hides_password_with_redirected_output():
    master, slave = pty.openpty()
    # A real controlling TTY, with captured stdout/stderr like rebuild frontends.
    program = """
import fcntl, os, termios
from lx_administration.storage.boot_password import secret
os.setsid()
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
assert secret('Boot password: ') == b'synthetic-terminal-password'
print('verified')
"""
    process = subprocess.Popen(
        [sys.executable, "-c", program],
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert select.select([master], [], [], 5)[0], "No terminal prompt"
        output = os.read(master, 4096)
        assert b"Boot password: " in output
        assert not termios.tcgetattr(slave)[3] & termios.ECHO
        os.write(master, b"synthetic-terminal-password\n")
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stderr.decode()
        assert stdout == b"verified\n" and not stderr
        while select.select([master], [], [], 0)[0]:
            output += os.read(master, 4096)
        assert b"synthetic-terminal-password" not in output
        assert termios.tcgetattr(slave)[3] & termios.ECHO
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()
        os.close(master)
        os.close(slave)


def test_passphrase_is_only_passed_through_memory_fd(monkeypatch):
    def invoke(args, **kwargs):
        assert NEW.decode() not in " ".join(args)
        assert "input" not in kwargs and "env" not in kwargs
        (fd,) = kwargs["pass_fds"]
        assert os.pread(fd, len(NEW), 0) == NEW
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(setup.subprocess, "run", invoke)
    assert setup.accepts("/dev/synthetic", NEW)


def test_failure_explains_terminal_and_target_generation(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["setup", "--device", "/dev/synthetic"])
    monkeypatch.setattr(setup.os, "geteuid", lambda: 0)
    monkeypatch.setattr(setup.os, "umask", lambda _: None)
    monkeypatch.setattr(setup.resource, "setrlimit", lambda *args: None)

    def no_terminal(*args, **kwargs):
        raise OSError("synthetic-private-detail")

    monkeypatch.setattr(setup, "prepare", no_terminal)
    with pytest.raises(SystemExit) as result:
        setup.main()
    assert result.value.code == 1
    error = capsys.readouterr().err
    assert "synthetic-private-detail" not in error
    assert "Ctrl+Alt+F3" in error and "ssh -t admin@HOST" in error
    assert "sudo ./result-boot/sw/bin/luxnix-setup-boot-password" in error
    assert 'sudo nixos-rebuild boot --flake ".#$(hostname)"' in error
    assert "No existing keyslots were removed" in error


def test_failed_add_keeps_recovery_and_has_no_success_receipt(disk, monkeypatch):
    before = setup.header_digest(disk)
    real = setup.cryptsetup

    def invoke(*args, **kwargs):
        if args[0] == "luksAddKey":
            return subprocess.CompletedProcess(args, 1, b"", b"")
        return real(*args, **kwargs)

    monkeypatch.setattr(setup, "cryptsetup", invoke)
    answers(monkeypatch, NEW, NEW, OLD)
    with pytest.raises(ValueError, match="Could not add"):
        setup.prepare(disk, change=True)
    assert setup.accepts(disk, OLD)
    assert setup.header_digest(disk) == before
    assert list(setup.STATE.glob("header-before-*/luks.header"))
    assert not (setup.STATE / "cryptroot.json").exists()


@pytest.mark.parametrize("missing", ["findmnt", "lsblk", "swapon", "cryptsetup"])
def test_missing_dependency_fails_before_state_or_keyslot_changes(tmp_path, monkeypatch, missing):
    monkeypatch.setattr(setup, "STATE", tmp_path / "state")
    monkeypatch.setattr(setup.shutil, "which", lambda name: None if name == missing else "/bin/" + name)
    monkeypatch.setattr(setup.boot, "verify_mount", lambda *args: pytest.fail("must preflight first"))
    with pytest.raises(ValueError, match="Missing required executable: " + missing):
        setup.prepare("/dev/synthetic")
    assert not setup.STATE.exists()


def test_ordinary_staging_never_adds_a_new_password(disk, monkeypatch):
    before = setup.header_digest(disk)
    answers(monkeypatch, NEW, NEW)
    with pytest.raises(ValueError, match="explicit --change"):
        setup.prepare(disk)
    assert setup.header_digest(disk) == before
    assert setup.accepts(disk, OLD)
    assert not (setup.STATE / "cryptroot.json").exists()
