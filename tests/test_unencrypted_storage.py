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


def test_only_gc10_retains_legacy_containers():
    expression = """
      let f = builtins.getFlake ("git+file://" + toString ./.);
          lib = f.inputs.nixpkgs.lib;
      in builtins.attrNames (lib.filterAttrs (_: h:
          h.config.luxnix.storage.operatorUnlocked.enable &&
          h.config.luxnix.storage.operatorUnlocked.layout == "legacy-containers")
          f.nixosConfigurations)
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    # Owner decision 2026-11-04: gc-10 keeps its installed containers. gc-09 keeps
    # them until its plaintext root is converted; every other inventory host selects
    # boot-luks.
    assert json.loads(result.stdout) == ["gc-09", "gc-10"]
