"""Evaluate gc-09's legacy storage graph for the boot cycle seen on 3 November 2026.

The real cold boot ordered nested bind mounts after their permission services,
those services after basic.target, and local-fs.target after the binds. systemd
then deleted D-Bus, tmpfiles and local-fs jobs. The VM lane in
tests/nixtest/operator_storage_migration_vm_test.nix proves the running graph;
this evaluation pins the host-level contract cheaply.
"""

import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]

EXPRESSION = r'''
  let f = builtins.getFlake "git+file://ROOT";
      lib = f.inputs.nixpkgs.lib;
      c = (f.nixosConfigurations.gc-09.extendModules { modules = [{
        luxnix.storage.operatorUnlocked.layout = lib.mkForce "legacy-containers";
      }]; }).config;
      s = c.luxnix.storage.operatorUnlocked;
      mounts = map (v: v.mountPoint) (builtins.attrValues s.volumes) ++ builtins.attrNames s.bindMounts;
      units = prefix: lib.filterAttrs (n: _: lib.hasPrefix prefix n) c.systemd.services;
  in {
    options = lib.genAttrs mounts (p: c.fileSystems.${p}.options);
    permissions = lib.mapAttrs (_: u: {
      default = u.unitConfig.DefaultDependencies or true;
      inherit (u) after wants requires;
    }) (units "luxnix-storage-permissions-");
    checks = lib.mapAttrs (_: u: u.serviceConfig.ExecStartPre or null) (units "luxnix-storage-check-");
    restackWanted = lib.mapAttrs (_: u: u.wants) (units "luxnix-storage-check-");
    paths = lib.mapAttrs (_: u: {
      default = u.unitConfig.DefaultDependencies or true;
      inherit (u) wantedBy;
    }) (lib.filterAttrs (n: _: lib.hasPrefix "lx-annotate" n) c.systemd.paths);
  }
'''.replace('ROOT', str(ROOT))


@pytest.fixture(scope='module')
def graph():
    return json.loads(subprocess.check_output(
        ['nix', 'eval', '--impure', '--json', '--expr', EXPRESSION], cwd=ROOT))


def test_storage_mounts_are_never_ordered_before_local_fs(graph):
    assert graph['options']
    for path, options in graph['options'].items():
        assert {'noauto', 'nofail', 'nodev', 'nosuid'} <= set(options), path


def test_permission_services_stay_out_of_basic_and_sysinit(graph):
    assert set(graph['permissions']) == {
        'luxnix-storage-permissions-luxnix-app-storage',
        'luxnix-storage-permissions-luxnix-secrets',
    }
    for name, unit in graph['permissions'].items():
        assert unit['default'] is False, name
        assert not {'basic.target', 'sysinit.target'} & set(unit['after'] + unit['wants'] + unit['requires']), name


def test_storage_path_units_do_not_hold_basic_target(graph):
    assert set(graph['paths']) == {'lx-annotate-filewatcher', 'lx-annotate-sap-import'}
    for name, unit in graph['paths'].items():
        assert unit['default'] is False and unit['wantedBy'] == ['multi-user.target'], name


def test_identity_gate_is_mandatory_only_for_nested_bind_consumers(graph):
    checks = graph['checks']
    gated = {name for name, command in checks.items() if command}
    assert 'luxnix-storage-check-vault-auth-setup' in gated
    assert 'luxnix-storage-check-lx-annotate' in gated
    assert 'luxnix-storage-check-postgresql' not in gated
    for name in gated:
        assert ' verify /' in checks[name], name
        # Restack stays optional so an unrelated rejection cannot block healthy volumes.
        assert graph['restackWanted'][name] == ['luxnix-storage-restack.service'], name
    vault = checks['luxnix-storage-check-vault-auth-setup']
    assert vault.endswith(' verify /etc/secrets /etc/secrets/vault')
