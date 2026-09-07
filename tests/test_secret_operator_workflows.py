import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
from unittest.mock import patch

import pytest
import yaml
from passlib.hash import sha512_crypt

from lx_administration.models.vault import load_admin_passwords

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts/vault/verify_admin_rotation.py"


def test_account_rotation_accepts_new_password_and_is_idempotent():
    verify = runpy.run_path(str(VERIFY))["verify"]
    payload = {
        "password": "synthetic replacement",
        "replacement_hash": sha512_crypt.hash("synthetic replacement"),
        "current_hash": sha512_crypt.hash("synthetic old"),
    }
    assert verify(payload) == "replacement"
    payload["current_hash"] = payload["replacement_hash"]
    assert verify(payload) == "already_current"


@pytest.mark.parametrize(
    "failure", ["reuse", "mismatch", "unknown-current", "unknown-new"]
)
def test_account_rotation_rejects_unsafe_pairs_without_secret_output(failure):
    payload = {
        "password": "synthetic replacement",
        "replacement_hash": sha512_crypt.hash("synthetic replacement"),
        "current_hash": sha512_crypt.hash("synthetic old"),
    }
    if failure == "reuse":
        payload["current_hash"] = sha512_crypt.hash(payload["password"])
    elif failure == "mismatch":
        payload["replacement_hash"] = sha512_crypt.hash("unrelated password")
    else:
        payload[
            "current_hash" if failure == "unknown-current" else "replacement_hash"
        ] = "invalid"
    result = subprocess.run(
        ["python", str(VERIFY)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    assert payload["password"] not in result.stdout + result.stderr
    assert payload["replacement_hash"] not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "content",
    [
        "",
        "admin_passwords: {}",
        "admin_passwords: {gc-05: null}",
        "admin_passwords: {gc-05: ''}",
        "admin_passwords: {'../bad': value}",
    ],
)
def test_strict_password_source_rejects_incomplete_rotation(tmp_path, content):
    source = tmp_path / "passwords.yml"
    source.write_text(content)
    source.chmod(0o600)
    with pytest.raises(ValueError):
        load_admin_passwords(source, strict=True)


def test_strict_password_source_rejects_world_readable_and_symlink(tmp_path):
    source = tmp_path / "passwords.yml"
    source.write_text("admin_passwords: {gc-05: synthetic}")
    source.chmod(0o644)
    with pytest.raises(ValueError):
        load_admin_passwords(source, strict=True)
    source.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(source)
    with pytest.raises(ValueError):
        load_admin_passwords(link, strict=True)
    assert load_admin_passwords(source, strict=True) == {"gc-05": "synthetic"}


@pytest.mark.parametrize("missing", ["key", "metadata"])
def test_existing_vault_cannot_be_reinitialized_on_missing_recovery_material(
    tmp_path, monkeypatch, missing
):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "existing-ciphertext").write_text("retained")
    if missing == "key":
        (vault / "vault.yml").write_text("secrets: []")
    key = tmp_path / "missing.key"
    script = ROOT / "scripts/bootstrap-lx-vault.py"
    namespace = runpy.run_path(str(script))
    monkeypatch.setattr(
        "sys.argv",
        [
            str(script),
            "--vault-dir",
            str(vault),
            "--vault-key",
            str(key),
            "--skip-sync",
        ],
    )
    with patch.dict(
        namespace["main"].__globals__,
        {"ensure_local_vault_key": lambda *_: pytest.fail("key creation reached")},
    ):
        with pytest.raises(ValueError):
            namespace["main"]()
    assert not key.exists()
    assert (vault / "existing-ciphertext").read_text() == "retained"


@pytest.mark.parametrize("name", ["rotate_admin_passwords", "deliver_hub_enrollment"])
def test_operator_playbooks_scope_root_and_secret_suppression(name):
    play = yaml.safe_load((ROOT / f"ansible/playbooks/{name}.yml").read_text())[0]
    assert play["vars"]["ansible_become_user"] == "root"
    assert play["vars"]["ansible_host_key_checking"] is True
    assert (
        "ansible_play_hosts_all | length == 1"
        in play["pre_tasks"][0]["ansible.builtin.assert"]["that"]
    )
    for task in play["tasks"]:
        if "block" in task:
            assert task["no_log"] is True
            assert task["diff"] is False


def test_secret_wrapper_uses_private_tmpfs_and_cleans_failed_transport(tmp_path):
    if not Path("/dev/shm").is_dir():
        pytest.skip("tmpfs fixture unavailable")
    transport = tmp_path / "transport"
    transport.write_text(
        "#!/bin/sh\n"
        'test -d "$ANSIBLE_LOCAL_TEMP" || exit 3\n'
        'test "$(stat -c %a "$ANSIBLE_LOCAL_TEMP")" = 700 || exit 4\n'
        'test "$ANSIBLE_HOST_KEY_CHECKING" = True || exit 5\n'
        'printf synthetic > "$ANSIBLE_LOCAL_TEMP/plaintext"\n'
        "exit 7\n"
    )
    transport.chmod(0o700)
    with tempfile.TemporaryDirectory(
        prefix="luxnix-secret-test-", dir="/dev/shm"
    ) as runtime:
        result = subprocess.run(
            [
                "bash",
                str(ROOT / "scripts/run-secret-playbook.sh"),
                "ansible/playbooks/deliver_hub_enrollment.yml",
                "--limit",
                "gc-05",
            ],
            env={
                **os.environ,
                "LUXNIX_SECRET_RUNTIME_DIR": runtime,
                "LUXNIX_UV_BIN": str(transport),
            },
            capture_output=True,
            text=True,
        )
        assert result.returncode == 7, result.stderr
        assert not list(Path(runtime).iterdir())


def test_secret_wrapper_rejects_unprotected_runtime(tmp_path):
    tmp_path.chmod(0o755)
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/run-secret-playbook.sh"), "unused"],
        env={**os.environ, "LUXNIX_SECRET_RUNTIME_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "private mode-0700" in result.stderr


@pytest.mark.parametrize(
    "answer, activated", [("y\n", True), ("n\n", False), ("yes\nn\n", False)]
)
def test_real_ansible_rotation_prompt_is_terminal_only(tmp_path, answer, activated):
    import fcntl
    import pty
    import select
    import termios
    import time

    password = "synthetic prompt credential"
    marker = tmp_path / "activated"
    log = tmp_path / "ansible.log"
    config = tmp_path / "ansible.cfg"
    config.write_text(
        "[defaults]\n"
        f'action_plugins = {ROOT / "ansible/playbooks/action_plugins"}\n'
        f"log_path = {log}\n"
    )
    playbook = tmp_path / "prompt.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "become": False,
                    "tasks": [
                        {
                            "name": "Approve",
                            "no_log": True,
                            "confirm_admin_rotation": {
                                "host": "gc-05",
                                "credential": {
                                    "password": password,
                                    "replacement_hash": sha512_crypt.hash(password),
                                    "current_hash": "!",
                                },
                            },
                        },
                        {
                            "name": "Synthetic activation marker",
                            "ansible.builtin.file": {
                                "path": str(marker),
                                "state": "touch",
                            },
                        },
                    ],
                }
            ]
        )
    )
    master, slave = pty.openpty()

    def controlling_terminal():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

    process = subprocess.Popen(
        ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            **os.environ,
            "ANSIBLE_CONFIG": str(config),
            "LUXNIX_ROTATION_TTY": os.ttyname(slave),
        },
        preexec_fn=controlling_terminal,
        pass_fds=(slave,),
    )
    transcript = b""
    try:
        deadline = time.monotonic() + 30
        while b"[y/n]:" not in transcript and time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                transcript += os.read(master, 65536)
            if process.poll() is not None:
                break
        assert b"Activate new admin password for machine gc-05?" in transcript
        assert transcript.count(password.encode()) == 1
        assert not marker.exists()
        os.write(master, answer.encode())
        stdout, stderr = process.communicate(timeout=30)
        assert (process.returncode == 0) == activated
        assert marker.exists() == activated
        assert password.encode() not in stdout + stderr
        assert password not in log.read_text()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        os.close(slave)


def test_rotation_confirmation_refuses_piped_yes_without_terminal(tmp_path):
    payload = {
        "password": "synthetic",
        "replacement_hash": sha512_crypt.hash("synthetic"),
        "current_hash": "!",
    }
    result = subprocess.run(
        [
            "python",
            "-c",
            "import json,sys; "
            "from lx_administration.models.vault.admin_rotation "
            "import confirm_on_terminal; "
            'confirm_on_terminal("gc-05", json.loads(sys.stdin.readline()))',
        ],
        input=json.dumps(payload) + "\ny\n",
        text=True,
        capture_output=True,
        env={k: v for k, v in os.environ.items() if k != "LUXNIX_ROTATION_TTY"},
        start_new_session=True,
    )
    assert result.returncode != 0
    assert payload["password"] not in result.stdout + result.stderr


def test_rotation_writes_only_the_approved_snapshot():
    play = yaml.safe_load(
        (ROOT / "ansible/playbooks/rotate_admin_passwords.yml").read_text()
    )[0]
    tasks = play["tasks"][0]["block"]
    approval = next(
        i for i, task in enumerate(tasks) if "confirm_admin_rotation" in task
    )
    for index, task in enumerate(tasks):
        if "ansible.builtin.copy" in task or "ansible.builtin.user" in task:
            assert index > approval
            assert "lookup(" not in str(task)
            assert "rotation_credential" in str(task)


def test_rotation_wrapper_rejects_piped_confirmation_before_transport(tmp_path):
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/run-secret-playbook.sh"),
            "ansible/playbooks/rotate_admin_passwords.yml",
            "--limit",
            "gc-05",
        ],
        input="y\n",
        text=True,
        capture_output=True,
        env={**os.environ, "LUXNIX_UV_BIN": str(tmp_path / "must-not-run")},
    )
    assert result.returncode == 2
    assert "interactive terminal" in result.stderr


def test_prompt_rejects_control_characters_before_opening_terminal(monkeypatch):
    from lx_administration.models.vault.admin_rotation import confirm_on_terminal

    payload = {
        "password": "synthetic\x1b[2J",
        "replacement_hash": sha512_crypt.hash("synthetic\x1b[2J"),
        "current_hash": "!",
    }
    monkeypatch.setattr(os, "open", lambda *_: pytest.fail("terminal opened"))
    with pytest.raises(ValueError, match="control characters"):
        confirm_on_terminal("gc-05", payload)
