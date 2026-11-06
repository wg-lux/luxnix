from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/tmux-inventory-session.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_default_dry_run_uses_the_canonical_inventory_group() -> None:
    result = _run("workspace", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Session: all-luxnix-dir" in result.stdout
    assert "Inventory group: tmux_hosts" in result.stdout
    assert "s-01: ssh -t admin@172.16.255.1" in result.stdout
    assert "gc-09: ssh -t admin@172.16.255.109" in result.stdout
    assert result.stdout.count("  ") == 7
    assert "no Tmux session created" in result.stdout


def test_group_and_user_can_be_overridden_with_an_isolated_config(tmp_path) -> None:
    inventory = tmp_path / "hosts.ini"
    inventory.write_text(
        """[all]
node-a ansible_host=10.0.0.1
node-b ansible_host=10.0.0.2

[operators]
node-b
"""
    )
    config = tmp_path / "tmux.yml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "inventory": {
                    "path": "hosts.ini",
                    "default_group": "operators",
                    "default_user": "admin",
                },
                "sessions": {
                    "shell": {
                        "name": "test-session",
                        "local_command": "zsh",
                        "remote_command": "exec zsh -l",
                    }
                },
            },
            sort_keys=False,
        )
    )

    result = _run(
        "shell",
        "--config",
        str(config),
        "--user",
        "operator",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert "node-b: ssh -t operator@10.0.0.2" in result.stdout
    assert "node-a:" not in result.stdout


def test_tmux_config_rejects_duplicate_keys_with_path(tmp_path) -> None:
    config = tmp_path / "ambiguous.yml"
    config.write_text(
        "schema_version: 1\nschema_version: 1\n", encoding="utf-8"
    )

    result = _run("workspace", "--config", str(config), "--dry-run")

    assert result.returncode != 0
    assert "duplicate key 'schema_version'" in result.stderr
    assert str(config) in result.stderr


def test_devenv_uses_one_tmux_launcher_without_hardcoded_addresses() -> None:
    devenv_scripts = (REPO_ROOT / "devenv/scripts.nix").read_text()
    launcher = SCRIPT.read_text()

    assert devenv_scripts.count("scripts/tmux-inventory-session.py") == 2
    assert "workspace" in devenv_scripts
    assert "monitor" in devenv_scripts
    assert "172.16.255." not in launcher
    assert not (REPO_ROOT / "tmux/all-luxnix-dir.sh").exists()
    assert not (REPO_ROOT / "tmux/init-server-ssh.sh").exists()
