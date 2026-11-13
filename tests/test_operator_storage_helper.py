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
        bootHost = (f.nixosConfigurations.gc-10.extendModules { modules = [{
          luxnix.storage.operatorUnlocked.layout = pkgs.lib.mkForce "boot-luks";
          luxnix.storage.operatorUnlocked.startupServices =
            pkgs.lib.mkForce [ "test-consumer" ];
        }]; }).config;
        bootHelper = builtins.head (builtins.filter
          (p: (p.name or "") == "luxnix-operator-storage")
          bootHost.environment.systemPackages);
      in [ (helper []) (helper [ "test-consumer" ]) bootHelper ]
    """
    result = subprocess.run(
        ["nix", "build", "--impure", "--no-link", "--json", "--expr", expression],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    # nix build JSON is ordered by derivation, not by the expression's list.
    ordered = subprocess.run(
        [
            "nix",
            "eval",
            "--impure",
            "--json",
            "--expr",
            f"map builtins.toString ({expression})",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )
    assert ordered.returncode == 0, ordered.stderr
    return [Path(path) for path in json.loads(ordered.stdout)]


@pytest.fixture
def run_helper(tmp_path):
    mocks = tmp_path / "bin"
    mocks.mkdir()
    calls = tmp_path / "calls"
    commands = {
        "id": "echo 0",
        "realpath": 'printf "%s\\n" "$2"',
        "cryptsetup": (
            'echo "cryptsetup $*" >> "$CALLS"; echo "loop: /recovery/fixture.luks"'
        ),
        "systemctl": 'echo "systemctl $*" >> "$CALLS"',
        "python3": 'echo "verify-storage" >> "$CALLS"; test "${FAIL_VERIFY:-0}" != 1',
    }
    for command, body in commands.items():
        path = mocks / command
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o700)

    def run(helper, *, fail_verify=False):
        source = (helper / "bin/luxnix-operator-storage").read_text()
        source = source.replace('if [ "$EUID" -ne 0 ]; then', "if false; then")
        source, count = re.subn(
            r"(?m)^export PATH=.*$",
            lambda m: m[0]
            + f"\nexport PATH={mocks}:$PATH\nexport CALLS={calls}"
            + f"\nexport FAIL_VERIFY={int(fail_verify)}",
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


def test_boot_luks_start_verifies_root_before_secondary_and_consumers(
    helpers, run_helper
):
    result, calls = run_helper(helpers[2])
    assert result.returncode == 0, result.stderr
    assert calls[0] == "verify-storage"
    assert "systemd-cryptsetup@luxnix\\x2dapp\\x2dstorage.service" in calls[1]
    assert "mount" in calls[2]
    assert calls[3:] == [
        "verify-storage",
        "systemctl --no-ask-password start test-consumer.service",
    ]


def test_boot_luks_start_refuses_wrong_root_before_any_unlock(helpers, run_helper):
    result, calls = run_helper(helpers[2], fail_verify=True)
    assert result.returncode != 0
    assert calls == ["verify-storage"]
