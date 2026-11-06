"""Exercise rotation ordering and failures without touching live hosts or secrets."""

import json
import os
from pathlib import Path
import subprocess

import pexpect
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "ansible/playbooks/rotate_hub_enrollment.yml"


def local_play(tmp_path, tasks):
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    play = tmp_path / "test.yml"
    play.write_text(
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
    command = ["ansible-playbook", "-i", "localhost,", "-c", "local", str(play)]
    return command, {**os.environ, "ANSIBLE_CONFIG": str(config)}


@pytest.mark.parametrize(
    "failure", ["", "auth", "offline", "managed", "issue", "result"]
)
def test_activation_stops_at_failed_stage(tmp_path, failure):
    commands = tmp_path / "commands"
    commands.mkdir()
    log = tmp_path / "calls.jsonl"
    mock = commands / "mock"
    mock.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as stream:
    stream.write(json.dumps([name, *args]) + '\\n')
failure = os.environ['FAILURE']
if name == 'luxnix-vault-enrollment-status':
    state = 'offline-cached' if failure == 'offline' else 'ready'
    print('Vault enrollment state: ' + state)
    sys.exit(0)
if name == 'luxnix-vault-reissue-hub-client-certificate':
    sys.exit(1 if failure == 'issue' else 0)
if args[0] == 'show':
    print('exit-code' if failure == 'result' else 'success')
elif args[1] == 'vault-auth-setup.service' and failure == 'auth':
    sys.exit(1)
elif args[1] == 'managed-secrets-setup.service' and failure == 'managed':
    sys.exit(1)
""")
    mock.chmod(0o755)
    for name in [
        "systemctl",
        "luxnix-vault-enrollment-status",
        "luxnix-vault-reissue-hub-client-certificate",
    ]:
        (commands / name).symlink_to(mock)
    workflow = yaml.safe_load(WORKFLOW.read_text())
    command, env = local_play(tmp_path, workflow[-1]["tasks"])
    env.update(PATH=f"{commands}:{env['PATH']}", CALL_LOG=str(log), FAILURE=failure)
    result = subprocess.run(
        command, env=env, capture_output=True, text=True, timeout=45
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    expected = [
        ["systemctl", "restart", "vault-auth-setup.service"],
        ["luxnix-vault-enrollment-status"],
        ["systemctl", "restart", "managed-secrets-setup.service"],
        ["luxnix-vault-reissue-hub-client-certificate"],
        [
            "systemctl",
            "show",
            "luxnix-vault-issue-hub-client-certificate.service",
            "--property=Result",
            "--value",
        ],
    ]
    if failure:
        stop = {"auth": 1, "offline": 2, "managed": 3, "issue": 4, "result": 5}[failure]
        assert calls == expected[:stop] + [["luxnix-vault-enrollment-status"]]
        assert result.returncode != 0
        assert "Activation failed." in result.stdout
        assert (
            "Fresh Vault authentication and certificate issuance succeeded"
            not in result.stdout
        )
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert calls == expected


@pytest.mark.parametrize(
    "answer,accepted",
    [("rotate localhost", True), ("no", False), ("", False), ("rotate gc-02", False)],
)
def test_interactive_consent_requires_exact_target(tmp_path, answer, accepted):
    workflow = yaml.safe_load(WORKFLOW.read_text())
    tasks = workflow[0]["tasks"][-2:]
    # Keep the real consent assertion and pause action; replace only display data.
    tasks[0]["ansible.builtin.pause"]["prompt"] = "Type rotate localhost to proceed"
    command, env = local_play(tmp_path, tasks)
    child = pexpect.spawn(
        command[0], command[1:], env=env, encoding="utf-8", timeout=30
    )
    child.expect("Type rotate localhost to proceed")
    child.sendline(answer)
    child.expect(pexpect.EOF)
    child.close()
    assert (child.exitstatus == 0) == accepted


def test_wrapper_rejects_noninteractive_rotation_before_delivery():
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/run-secret-playbook.sh"),
            str(WORKFLOW),
            "--limit",
            "gc-02",
        ],
        input="rotate gc-02\n",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "requires an interactive terminal" in result.stderr
