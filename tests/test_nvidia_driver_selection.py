"""Evaluate fleet NVIDIA policy without building or activating host systems."""

import json
from pathlib import Path
import shutil
import subprocess
import warnings

import pytest

ROOT = Path(__file__).resolve().parents[1]


def evaluate(body: str) -> subprocess.CompletedProcess[str]:
    if shutil.which("nix") is None:
        pytest.skip("Nix is required for NVIDIA configuration evaluation")
    expression = f"""
      let
        flake = builtins.getFlake {json.dumps(f"git+file://{ROOT}")};
        lib = flake.inputs.nixpkgs.lib;
      in {body}
    """
    return subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )


def policy_for(host: str, module: str = ""):
    result = evaluate(
        r"""
      let
        n = flake.nixosConfigurations.__HOST__.extendModules {
          modules = [ { __MODULE__ } ];
        };
        c = n.config;
        prime = c.luxnix.nvidia-prime;
        standard = c.luxnix.nvidia-default;
        branch = if prime.enable then prime.nvidiaDriver else standard.nvidiaDriver;
      in {
        shared = c.luxnix.generic-settings.gpu.nvidia.driver;
        prime = prime.nvidiaDriver;
        standard = standard.nvidiaDriver;
        enabled = prime.enable || standard.enable;
        matches = !(prime.enable || standard.enable) ||
          c.hardware.nvidia.package.drvPath ==
            c.boot.kernelPackages.nvidiaPackages.${branch}.drvPath;
        failures = map (a: a.message)
          (builtins.filter (a: !a.assertion) c.assertions);
      }
    """.replace("__HOST__", json.dumps(host)).replace("__MODULE__", module)
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_every_host_has_consistent_driver_selection():
    result = evaluate("builtins.attrNames flake.nixosConfigurations")
    assert result.returncode == 0, result.stderr
    hosts = json.loads(result.stdout)
    assert {"gc-10", "gs-01", "gs-02"} <= set(hosts)
    # Separate processes bound evaluator memory independently of fleet size.
    for host in hosts:
        policy = policy_for(host)
        assert policy["shared"] == "production", host
        assert policy["prime"] == policy["standard"] == policy["shared"], host
        assert policy["matches"], host
        nvidia_failures = [
            message for message in policy["failures"] if "nvidia" in message.lower()
        ]
        assert nvidia_failures == [], (host, nvidia_failures)
        if policy["failures"]:
            warnings.warn(
                f"Unrelated host assertions on {host}: {policy['failures']}",
                stacklevel=1,
            )


@pytest.mark.parametrize("host", ["gc-10", "gs-01", "gs-02"])
@pytest.mark.parametrize("branch", ["stable", "beta", "production"])
def test_explicit_branch_controls_package(host, branch):
    policy = policy_for(
        host,
        "luxnix.generic-settings.gpu.nvidia.driver = "
        f"lib.mkForce {json.dumps(branch)};",
    )
    assert policy["enabled"]
    assert policy["prime"] == policy["standard"] == branch
    assert policy["matches"]
    assert policy["failures"] == []


def test_conflicting_enabled_modules_fail_assertion():
    policy = policy_for(
        "gs-02",
        """
      luxnix.nvidia-prime.nvidiaDriver = lib.mkForce "beta";
      luxnix.nvidia-default.nvidiaDriver = lib.mkForce "production";
    """,
    )
    assert any(
        "must select the same nvidiaDriver branch" in message
        for message in policy["failures"]
    )


@pytest.mark.parametrize(
    "option",
    [
        "generic-settings.gpu.nvidia.driver",
        "nvidia-prime.nvidiaDriver",
        "nvidia-default.nvidiaDriver",
    ],
)
def test_invalid_driver_branch_is_rejected(option):
    result = evaluate(f"""
      (flake.nixosConfigurations.gc-10.extendModules {{
        modules = [{{ luxnix.{option} = lib.mkForce "unsupported"; }}];
      }}).config.luxnix.{option}
    """)
    assert result.returncode != 0
    assert "unsupported" in result.stderr
    assert "one of" in result.stderr


@pytest.mark.parametrize(
    "action, loaded, expected, code",
    [
        ("test", "595.45.04", "595.71.05", 1),
        ("switch", "595.45.04", "595.71.05", 1),
        ("switch", "595.71.05", "595.71.05", 0),
        ("boot", "595.45.04", "595.71.05", 0),
        ("switch", None, "595.71.05", 0),
    ],
)
def test_loaded_driver_guard(tmp_path, action, loaded, expected, code):
    source = (ROOT / "modules/nixos/luxnix/generic-settings/default.nix").read_text()
    script = source.split("system.preSwitchChecks.nvidiaDriver =", 1)[1]
    script = script.split(") ''\n", 1)[1].split("    '';", 1)[0]
    version_file = tmp_path / "version"
    if loaded is not None:
        version_file.write_text(loaded + "\n")
    script = script.replace("/sys/module/nvidia/version", str(version_file))
    script = script.replace("''${2-}", "${2-}")
    script = script.replace(
        "${lib.escapeShellArg config.hardware.nvidia.package.version}", expected
    )
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script, "_", "/incoming", action],
        capture_output=True, text=True,
    )
    assert result.returncode == code, result.stderr
    if code:
        assert "nixos-rebuild boot" in result.stderr
