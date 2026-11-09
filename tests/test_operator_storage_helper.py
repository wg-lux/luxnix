"""Build the actual recovery helper with ShellCheck enabled, without a host closure."""

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def helpers():
    if shutil.which("nix") is None:
        pytest.skip("Nix build required")
    expression = r"""
      let
        f = builtins.getFlake ("git+file://" + builtins.toString ./.);
        pkgs = f.inputs.nixpkgs.legacyPackages.x86_64-linux;
        helper = startupServices: let
          m = import ./modules/nixos/luxnix/operator-storage-helper/default.nix {
            inherit pkgs;
            lib = pkgs.lib;
            utils.escapeSystemdPath = x: x;
            config.luxnix.storage.operatorUnlocked = {
              enable = true;
              layout = "legacy-containers";
              unlockMethod = "tpm2";
              volumes.fixture = {
                device = "/dev/mapper/fixture";
                container = "/recovery/fixture.luks";
                depends = [];
              };
              inherit startupServices;
            };
          };
        in builtins.head m.config.content.environment.systemPackages;
      in [ (helper []) (helper [ "test-consumer" ]) ]
    """
    result = subprocess.run(
        ["nix", "build", "--impure", "--no-link", "--json", "--expr", expression],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    return [Path(item["outputs"]["out"]) for item in json.loads(result.stdout)]


@pytest.fixture
def run_helper(tmp_path):
    mocks = tmp_path / "bin"
    mocks.mkdir()
    calls = tmp_path / "calls"
    commands = {
        "id": "echo 0",
        "realpath": 'printf "%s\\n" "$2"',
        "cryptsetup": (
            'echo "cryptsetup $*" >> "$CALLS"; '
            'echo "loop: /recovery/fixture.luks"'
        ),
        "systemctl": 'echo "systemctl $*" >> "$CALLS"',
    }
    for command, body in commands.items():
        path = mocks / command
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o700)

    def run(helper):
        source = (helper / "bin/luxnix-operator-storage").read_text()
        source, count = re.subn(
            r"(?m)^export PATH=.*$",
            lambda m: m[0] + f"\nexport PATH={mocks}:$PATH\nexport CALLS={calls}",
            source,
        )
        assert count == 1
        executable = tmp_path / "helper"
        executable.write_text(source)
        executable.chmod(0o700)
        result = subprocess.run(
            [str(executable), "start"], text=True, capture_output=True
        )
        return result, calls.read_text().splitlines() if calls.exists() else []

    return run


def test_empty_startup_builds_and_refuses_without_unlocking(helpers, run_helper):
    result, calls = run_helper(helpers[0])
    assert result.returncode == 1
    assert "No startupServices configured" in result.stderr
    assert calls == []


def test_populated_startup_verifies_backing_before_consumers(helpers, run_helper):
    result, calls = run_helper(helpers[1])
    assert result.returncode == 0, result.stderr
    assert calls == [
        "cryptsetup status fixture",
        "systemctl --no-ask-password start test-consumer.service",
    ]
