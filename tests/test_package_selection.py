"""Package policy merges scopes without enabling unrelated role behavior."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_package_scopes_merge_deduplicate_and_validate():
    expression = r"""
      let
        f = builtins.getFlake ("git+file://" + builtins.toString ./.);
        lib = f.inputs.nixpkgs.lib.extend (final: _: {
          luxnix = import ./lib/module/default.nix { lib = final; };
        });
        pkgs = f.nixosConfigurations.gc-02.pkgs;
        evaluate = modules: (lib.evalModules {
          specialArgs = { inherit pkgs; };
          modules = [
            ./modules/nixos/roles/custom-packages/default.nix
            {
              options = {
                environment.systemPackages = lib.mkOption {
                  type = lib.types.listOf lib.types.package; default = [];
                };
                cli = lib.mkOption { type = lib.types.attrs; default = {}; };
                programs = lib.mkOption { type = lib.types.attrs; default = {}; };
                hardware = lib.mkOption { type = lib.types.attrs; default = {}; };
              };
            }
          ] ++ modules;
        }).config;
        base = { luxnix.packages = {
          shared = [ pkgs.hello ];
          roles.analysis = [ pkgs.jq pkgs.hello ];
          machine = [ pkgs.lx-annotate pkgs.jq ];
        }; };
        c = evaluate [ base ];
        extended = evaluate [ base {
          luxnix.packages.roles.analysis = [ pkgs.ripgrep ];
        } ];
        enabled = evaluate [{ roles.custom-packages.enable = true; }];
        paths = c: map toString c.environment.systemPackages;
      in {
        actual = paths c;
        expected = map toString [ pkgs.hello pkgs.jq pkgs.lx-annotate ];
        extension = paths extended;
        extendedExpected = map toString [
          pkgs.hello pkgs.jq pkgs.ripgrep pkgs.lx-annotate
        ];
        disabledContributions = c.luxnix.packages.roles;
        enabledContribution =
          builtins.hasAttr "custom-packages" enabled.luxnix.packages.roles;
        invalid = builtins.tryEval (builtins.deepSeq (paths (evaluate [{
          luxnix.packages.machine = [ "jq" ];
        }])) true);
      }
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=True,
    )
    data = json.loads(result.stdout)
    assert data["actual"] == data["expected"]
    assert sorted(data["extension"]) == sorted(data["extendedExpected"])
    assert set(data["disabledContributions"]) == {"analysis"}
    assert data["enabledContribution"]
    assert data["invalid"]["success"] is False
