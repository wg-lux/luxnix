"""Evaluate opt-in upgrade admission without building or activating a host."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which('nix') is None, reason='Nix evaluation required')
def test_scheduled_upgrades_require_pinned_boot_without_reboot():
    expression = r'''
    let
      flake = builtins.getFlake ("git+file://" + builtins.toString ./.);
      lib = flake.inputs.nixpkgs.lib.extend (_: _: { luxnix.mkBoolOpt = default: description:
        lib.mkOption { inherit default description; type = lib.types.bool; }; });
      evaluate = settings: let c = (lib.evalModules {
        modules = [
          ./modules/nixos/luxnix/maintenance/audo-update/default.nix
          ({ lib, ... }: {
            options.assertions = lib.mkOption { type = lib.types.listOf lib.types.attrs; default = []; };
            options.system.autoUpgrade = lib.mkOption { type = lib.types.attrs; default = {}; };
            config.luxnix.maintenance.autoUpdates = settings;
          })
        ];
      }).config; in {
        failures = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
        upgrade = c.system.autoUpgrade;
      };
      pin = "github:wg-lux/luxnix/" + builtins.concatStringsSep "" (lib.replicate 40 "a");
    in {
      disabled = evaluate {};
      missing = evaluate { enable = true; };
      moving = evaluate { enable = true; flake = "github:wg-lux/luxnix/prototype"; };
      switching = evaluate { enable = true; flake = pin; operation = "switch"; };
      pinned = evaluate { enable = true; flake = pin; };
    }
    '''
    result = subprocess.run(['nix', 'eval', '--impure', '--json', '--expr', expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr
    cases = json.loads(result.stdout)
    assert cases['disabled'] == {'failures': [], 'upgrade': {}}
    for case in ('missing', 'moving', 'switching'):
        assert cases[case]['failures'], case
    assert cases['pinned']['failures'] == []
    upgrade = cases['pinned']['upgrade']
    assert upgrade['operation'] == 'boot'
    assert upgrade['allowReboot'] is False
    assert '--no-update-lock-file' in upgrade['flags']


def test_shared_inventory_requires_explicit_revision_for_opt_in():
    settings = yaml.safe_load((ROOT / 'ansible/inventory/group_vars/all/30-nix.yml').read_text())['group_luxnix']
    assert 'maintenance.autoUpdates.flake' not in settings
    assert settings['maintenance.autoUpdates.operation'] == '"boot"'
