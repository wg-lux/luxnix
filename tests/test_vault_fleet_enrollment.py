"""Exercise repeat/recovery paths with an isolated recording Vault, never production."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/vault"))
spec = importlib.util.spec_from_file_location(
    "ensure_site_enrollment", ROOT / "scripts/vault/ensure_site_enrollment.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SITE = "gc-09.intern"
CREDENTIALS = {
    "approle_role_id": "synthetic-role",
    "approle_secret_id": "synthetic-secret",
    "source-node-secret": "synthetic-node",
}


@pytest.fixture(scope="module")
def trust(tmp_path_factory):
    directory = tmp_path_factory.mktemp("fleet-crypto")
    key = subprocess.run(
        ["openssl", "genpkey", "-algorithm", "X25519"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    public = subprocess.run(
        ["openssl", "pkey", "-pubout"],
        input=key,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=fleet-test",
            "-keyout",
            str(directory / "key"),
            "-out",
            str(directory / "ca"),
        ],
        capture_output=True,
        check=True,
    )
    return (directory / "ca").read_text(), public


class RecordingVault:
    def __init__(self, public):
        self.public = public
        self.calls = []
        self.failure = None
        self.node = CREDENTIALS["source-node-secret"]

    def call(self, verb, path, payload=None, **kwargs):
        self.calls.append((verb, path, payload))
        if self.failure and self.failure in path:
            raise module.LifecycleError("controlled failure")
        if path.endswith("/role-id"):
            return {"data": {"role_id": CREDENTIALS["approle_role_id"]}}
        if "/nodes/" in path:
            return {"data": {"data": {"shared_secret": self.node}}}
        if path.endswith("/secret-id/lookup"):
            assert payload == {"secret_id": CREDENTIALS["approle_secret_id"]}
            return {"data": {"secret_id_accessor": "synthetic-accessor"}}
        if path.endswith("/current"):
            return {"data": {"data": {"public_key": self.public}}}
        raise AssertionError(path)


def enroll(tmp_path, trust, monkeypatch):
    ca, public = trust
    vault = RecordingVault(public)
    monkeypatch.setattr(module, "Vault", lambda: vault)
    commands = []

    def checked(command):
        commands.append(command)
        if command[0] == "luxnix-vault-enroll-hub-site":
            path = Path(command[2])
            path.mkdir(mode=0o700)
            for name, value in CREDENTIALS.items():
                module.durable_write(path / name, value)

    monkeypatch.setattr(module, "checked", checked)
    payload = {
        "site": SITE,
        "installed": {},
        "kv_mount": "kv",
        "recipient_path": "hub/current",
    }
    state, bundles, receiver = [
        tmp_path / name for name in ("state", "bundles", "receiver")
    ]
    receiver.mkdir()

    def run():
        return module.reconcile(payload, state, bundles, receiver, ca)

    return run, payload, vault, commands, state, bundles, receiver


def test_first_enrollment_retry_and_lost_site_reuse_one_identity(
    tmp_path, trust, monkeypatch
):
    run, payload, vault, commands, _, bundles, _ = enroll(tmp_path, trust, monkeypatch)
    assert run()["changed"]
    before = {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in (bundles / "gc-09").iterdir()
    }
    assert not run()["changed"]  # interrupted delivery: nothing on site yet
    payload["installed"] = CREDENTIALS.copy()
    assert not run()["changed"]  # complete previous deployment
    assert [c[0] for c in commands].count("luxnix-vault-enroll-hub-site") == 1
    after = {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in (bundles / "gc-09").iterdir()
    }
    assert before == after
    assert not any(path.endswith("/secret-id") for _, path, _ in vault.calls)
    assert all(p.stat().st_mode & 0o777 == 0o400 for p in (bundles / "gc-09").iterdir())


def test_adopts_existing_site_without_issuing_credentials(tmp_path, trust, monkeypatch):
    run, payload, _, commands, _, bundles, _ = enroll(tmp_path, trust, monkeypatch)
    payload["installed"] = CREDENTIALS.copy()
    assert run()["changed"]
    assert all(c[0] != "luxnix-vault-enroll-hub-site" for c in commands)
    assert (bundles / "gc-09/approle_secret_id").read_text().strip() == CREDENTIALS[
        "approle_secret_id"
    ]


@pytest.mark.parametrize(
    "kind",
    [
        "contained",
        "conflict",
        "revoked",
        "missing-node",
        "bad-public-key",
        "receiver-conflict",
        "partial",
        "symlink",
        "permissions",
    ],
)
def test_failures_never_issue_replacements(tmp_path, trust, monkeypatch, kind):
    run, payload, vault, commands, state, bundles, receiver = enroll(
        tmp_path, trust, monkeypatch
    )
    run()
    commands.clear()
    if kind == "contained":
        (state / module.identity(SITE)).write_text("{}")
    elif kind == "conflict":
        payload["installed"] = {"approle_secret_id": "different"}
    elif kind == "revoked":
        vault.failure = "/secret-id/lookup"
    elif kind == "missing-node":
        vault.node = None
    elif kind == "bad-public-key":
        vault.public = "not a key"
    elif kind == "receiver-conflict":
        module.durable_write(receiver / "gc-09-source-node-secret", "different")
    elif kind == "partial":
        (bundles / "gc-09/approle_secret_id").unlink()
    elif kind == "symlink":
        file = bundles / "gc-09/approle_secret_id"
        file.rename(file.with_suffix(".saved"))
        file.symlink_to(file.with_suffix(".saved"))
    else:
        (bundles / "gc-09").chmod(0o755)
    with pytest.raises(module.LifecycleError):
        run()
    assert all(c[0] != "luxnix-vault-enroll-hub-site" for c in commands)
    if kind == "contained":
        assert commands == []


def test_recovers_missing_role_id_from_valid_saved_secret(tmp_path, trust, monkeypatch):
    run, _, _, commands, _, bundles, _ = enroll(tmp_path, trust, monkeypatch)
    run()
    (bundles / "gc-09/approle_role_id").unlink()
    commands.clear()
    assert run()["changed"]
    assert all(c[0] != "luxnix-vault-enroll-hub-site" for c in commands)


def test_rejects_piped_token_and_arbitrary_arguments():
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/enroll-reachable-hub-sites.sh")],
        input="synthetic-secret",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "synthetic-secret" not in result.stdout + result.stderr


def test_cli_errors_never_echo_secret_input():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/vault/ensure_site_enrollment.py")],
        input=json.dumps({"token": "synthetic secret"}),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    assert "synthetic secret" not in result.stdout + result.stderr


def test_fleet_scope_transport_and_secret_blocks():
    plays = yaml.safe_load(
        (ROOT / "ansible/playbooks/enroll_reachable_hub_sites.yml").read_text()
    )
    assert (
        plays[0]["hosts"]
        == plays[2]["hosts"]
        == "active_clients:&gpu_client:&endoreg_client"
    )
    assert plays[2]["serial"] == 1
    secret_tasks = yaml.safe_load(
        (ROOT / "ansible/playbooks/tasks/hub_enrollment_reconcile.yml").read_text()
    )
    assert secret_tasks[0]["no_log"] and secret_tasks[0]["diff"] is False
    assert "always" in secret_tasks[0]
    prompt = next(t for t in plays[1]["tasks"] if "ansible.builtin.pause" in t)
    assert prompt["no_log"] and prompt["ansible.builtin.pause"]["echo"] is False
    bootstrap = next(t for t in plays[1]["tasks"] if "ansible.builtin.shell" in t)
    assert bootstrap["no_log"] and "stdin" in bootstrap["args"]
    assert "fleet_admin_token" not in bootstrap["ansible.builtin.shell"]
    wrapper = (ROOT / "scripts/enroll-reachable-hub-sites.sh").read_text()
    assert "StrictHostKeyChecking=yes" in wrapper
    assert "ANSIBLE_REMOTE_TEMP=/dev/shm" in wrapper
    assert "run-secret-playbook.sh" in wrapper


@pytest.mark.parametrize(
    "status,expected",
    [
        ("unreachable", 0),
        ("enrolled", 0),
        ("failed-enrollment", 2),
        ("failed-preflight", 2),
    ],
)
def test_real_ansible_summary_reports_failures_and_skips_offline(
    tmp_path, status, expected
):
    """Execute the real reporting play locally; no SSH or production inventory."""
    ansible = ROOT / ".devenv/state/venv/bin/ansible-playbook"
    if not ansible.exists():
        pytest.skip("Ansible development environment unavailable")
    plays = yaml.safe_load(
        (ROOT / "ansible/playbooks/enroll_reachable_hub_sites.yml").read_text()
    )
    summary = tmp_path / "summary.yml"
    summary.write_text(yaml.safe_dump([plays[-1]]))
    inventory = tmp_path / "inventory.yml"
    inventory.write_text(
        yaml.safe_dump(
            {
                "all": {
                    "hosts": {
                        "gs-02": {
                            "ansible_connection": "local",
                            "fleet_admin_token": {
                                "user_input": "synthetic-sensitive-token"
                            },
                        },
                        "gc-09": {"fleet_enrollment_status": status},
                    },
                    "children": {
                        group: {"hosts": {"gc-09": {}}}
                        for group in ["active_clients", "gpu_client", "endoreg_client"]
                    },
                }
            }
        )
    )
    env = dict(
        __import__("os").environ,
        ANSIBLE_CONFIG=str(ROOT / "conf/connectivity-ansible.cfg"),
        ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-tmp"),
    )
    env.pop("ANSIBLE_LOG_PATH", None)
    result = subprocess.run(
        [str(ansible), "-i", str(inventory), str(summary)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert "synthetic-sensitive-token" not in result.stdout + result.stderr
    assert f"gc-09: {status}" in result.stdout


def test_real_hidden_token_prompt_does_not_log_input(tmp_path):
    import fcntl
    import termios
    import os
    import pty
    import select
    import time

    ansible = ROOT / ".devenv/state/venv/bin/ansible-playbook"
    if not ansible.exists():
        pytest.skip("Ansible development environment unavailable")
    plays = yaml.safe_load(
        (ROOT / "ansible/playbooks/enroll_reachable_hub_sites.yml").read_text()
    )
    tasks = [
        task
        for task in plays[1]["tasks"]
        if "ansible.builtin.pause" in task
        or task["name"] == "Validate token input without logging it"
    ]
    playbook = tmp_path / "prompt.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "become": False,
                    "tasks": tasks,
                }
            ]
        )
    )
    log = tmp_path / "ansible.log"
    config = tmp_path / "ansible.cfg"
    config.write_text(f"[defaults]\nlog_path = {log}\n")
    token = b"hvs.synthetic-fleet-test-token"
    master, slave = pty.openpty()

    def controlling_terminal():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

    process = subprocess.Popen(
        [str(ansible), "-i", "localhost,", "-c", "local", str(playbook)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=dict(os.environ, ANSIBLE_CONFIG=str(config)),
        preexec_fn=controlling_terminal,
    )
    transcript = b""
    try:
        deadline = time.monotonic() + 15
        while (
            b"Vault admin token (hidden" not in transcript
            and time.monotonic() < deadline
        ):
            if select.select([master], [], [], 0.1)[0]:
                transcript += os.read(master, 65536)
        assert b"Vault admin token (hidden" in transcript, transcript.decode()
        # Ansible prints before flushing pending input and disabling echo.
        # Wait for its terminal mode transition before simulating typing.
        while termios.tcgetattr(slave)[3] & termios.ECHO:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        os.write(master, token + b"\r")
        process.wait(timeout=15)
        while select.select([master], [], [], 0.1)[0]:
            transcript += os.read(master, 65536)
        assert process.returncode == 0, transcript.decode()
        assert token not in transcript
        assert token.decode() not in log.read_text()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        os.close(slave)


@pytest.mark.parametrize(
    "change", [None, "checksum", "mode", "group", "symlink", "missing"]
)
def test_real_ansible_installer_runs_only_for_content_or_permission_changes(
    tmp_path, change
):
    import copy
    import os

    ansible = ROOT / ".devenv/state/venv/bin/ansible-playbook"
    if not ansible.exists():
        pytest.skip("Ansible development environment unavailable")
    block = yaml.safe_load(
        (ROOT / "ansible/playbooks/tasks/hub_enrollment_delivery.yml").read_text()
    )[0]["block"]
    tasks = [
        task
        for task in block
        if task["name"]
        in [
            "Determine whether installation is needed",
            "Check content, ownership and permissions",
        ]
    ]
    files = [
        "approle_role_id",
        "approle_secret_id",
        "vault-server-ca.pem",
        "source-node-secret",
    ]
    stats = [
        {
            "stat": {
                "isreg": True,
                "islnk": False,
                "uid": 0,
                "checksum": "same-content",
                "mode": "0644"
                if name == "vault-server-ca.pem"
                else "0640"
                if name == "source-node-secret"
                else "0400",
                "gr_name": "sensitiveServices"
                if name == "source-node-secret"
                else "root",
            }
        }
        for name in files
    ]
    destination = copy.deepcopy(stats)
    field = {
        "checksum": ("checksum", "changed-content"),
        "mode": ("mode", "0644"),
        "group": ("gr_name", "unexpected"),
        "symlink": ("islnk", True),
    }
    if change == "missing":
        destination[0]["stat"] = {}
    elif change:
        key, value = field[change]
        destination[0]["stat"][key] = value
    tasks.append(
        {
            "ansible.builtin.assert": {
                "that": "enrollment_install_needed == "
                + ("true" if change else "false")
            }
        }
    )
    play = {
        "hosts": "localhost",
        "gather_facts": False,
        "become": False,
        "vars": {
            "enrollment_files": files,
            "enrollment_inputs": {"results": stats},
            "enrollment_destinations": {"results": destination},
        },
        "tasks": tasks,
    }
    path = tmp_path / "comparison.yml"
    path.write_text(yaml.safe_dump([play]))
    result = subprocess.run(
        [str(ansible), "-i", "localhost,", "-c", "local", str(path)],
        capture_output=True,
        text=True,
        env=dict(
            os.environ, ANSIBLE_CONFIG=str(ROOT / "conf/connectivity-ansible.cfg")
        ),
    )
    assert result.returncode == 0, result.stdout + result.stderr
