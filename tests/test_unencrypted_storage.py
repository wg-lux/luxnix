"""The sole new-install layout is boot LUKS; existing recovery stays available."""

import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("host", ["gc-09", "gs-02"])
def test_retired_plain_root_is_rejected(host):
    expression = f"""
      let f = builtins.getFlake ("git+file://" + toString ./.);
          h = f.nixosConfigurations.{host}.extendModules {{
            modules = [({{ lib, ... }}: {{
            luxnix.storage.operatorUnlocked.layout = lib.mkForce "unencrypted-root";
          }})]; }};
      in h.config.luxnix.storage.operatorUnlocked.layout
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode != 0
    assert "unencrypted-root" in result.stderr and "type" in result.stderr


def test_existing_recovery_is_bounded_to_two_hosts():
    expression = """
      let f = builtins.getFlake ("git+file://" + toString ./.);
          lib = f.inputs.nixpkgs.lib;
          bad = f.nixosConfigurations.gs-02.extendModules { modules = [{
            luxnix.storage.operatorUnlocked.layout = lib.mkForce "legacy-containers";
          }]; };
      in {
        legacy = builtins.attrNames (lib.filterAttrs (_: h:
          h.config.luxnix.storage.operatorUnlocked.enable &&
          h.config.luxnix.storage.operatorUnlocked.layout == "legacy-containers")
          f.nixosConfigurations);
        failures = map (a: a.message)
          (builtins.filter (a: !a.assertion) bad.config.assertions);
      }
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    configuration = json.loads(result.stdout)
    assert configuration["legacy"] == ["gc-09", "gc-10"]
    assert any(
        "recovery compatibility for gc-09/gc-10 only" in f
        for f in configuration["failures"]
    )
