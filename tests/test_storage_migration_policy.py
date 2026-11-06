"""Migration scope is reviewed configuration checked against effective fleet declarations."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from lx_administration.storage import migration_policy as policy

ROOT = Path(__file__).resolve().parents[1]


def test_policy_is_yaml_compatible_and_shared_by_snapshot_and_archive():
    path = ROOT / 'lx_administration/storage/migration-policy.yml'
    assert yaml.safe_load(path.read_text()) == policy.load_policy()
    from lx_administration.storage import snapshot, migration_archive
    assert migration_archive.validate_snapshot is policy.validate_snapshot
    assert snapshot.writer is policy.writer
    assert snapshot.INNER == policy.inner_mounts()
    for host in policy.supported_hosts():
        for name, source in policy.snapshot_sources(host).items():
            policy.validate_snapshot(host, 'reviewed-01', {
                'name': name, 'source': source,
                'snapshot': f'{policy.snapshot_parent(source, "reviewed-01")}/{name}'})


def test_unreviewed_hosts_components_and_paths_are_rejected():
    with pytest.raises(ValueError, match='reviewed migration coverage'):
        policy.snapshot_sources('new-host')
    for item in [dict(name='archive', source='/archive', snapshot='/archive/snapshot'),
                 dict(name='root', source='/', snapshot='/other/root')]:
        with pytest.raises(ValueError):
            policy.validate_snapshot('gc-09', 'reviewed-01', item)
    assert not policy.writer('sshd.service')
    assert not policy.writer('postgresql.socket')
    assert policy.writer('managed-secrets-setup.service')
    assert policy.writer('postgres-endoreg-setup.service')
    assert policy.writer('postgresqlBackup-example.timer')


def test_missing_or_invalid_policy_fails_closed(tmp_path):
    path = tmp_path / 'policy.yml'
    with pytest.raises(FileNotFoundError):
        policy.load_policy(path)
    path.write_text('{}')
    with pytest.raises(ValueError, match='policy'):
        policy.load_policy(path)
    data = policy.load_policy()
    data['hosts']['new-host'] = {'invalid': '/srv/../other'}
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='source path'):
        policy.load_policy(path)


@pytest.mark.skipif(not shutil.which('nix'), reason='Nix evaluation required for effective fleet policy')
def test_effective_fleet_writers_and_legacy_protected_mounts_are_covered():
    expression = r'''
      let f = builtins.getFlake ("git+file://" + builtins.toString ./.);
      in builtins.mapAttrs (_: h: let c = h.config; in {
        layout = c.luxnix.storage.operatorUnlocked.layout;
        guarded = builtins.attrNames c.luxnix.storage.operatorUnlocked.guardedServices;
        protected = builtins.concatLists (builtins.attrValues c.luxnix.storage.operatorUnlocked.guardedServices);
        mounts = builtins.mapAttrs (_: v: { inherit (v) fsType device; }) c.fileSystems;
        volumes = builtins.mapAttrs (_: v: { inherit (v) container mountPoint; })
          c.luxnix.storage.operatorUnlocked.volumes;
      }) f.nixosConfigurations
    '''
    result = subprocess.run(['nix', 'eval', '--impure', '--json', '--expr', expression],
                            cwd=ROOT, text=True, capture_output=True, timeout=240)
    assert result.returncode == 0, result.stderr
    fleet = json.loads(result.stdout)
    for host, declaration in fleet.items():
        missing = [name for name in declaration['guarded'] if not policy.writer(name + '.service')]
        assert not missing, f'{host}: declare new protected writers in migration-policy.yml: {missing}'
        if declaration['layout'] != 'legacy-containers':
            continue
        sources = set(policy.snapshot_sources(host).values())
        # Each Btrfs subvolume is independent: archiving / does not cover a new
        # mount below it. Swap has no application state to preserve.
        required = {path for path, mount in declaration['mounts'].items()
                    if mount['fsType'] == 'btrfs' and path != '/swap'}
        assert required <= sources, f'{host}: missing protected mount snapshots: {required - sources}'
        assert {volume['mountPoint'] for volume in declaration['volumes'].values()} <= set(policy.inner_mounts())
        for volume in declaration['volumes'].values():
            parents = [path for path in declaration['mounts'] if
                       Path(volume['container']).is_relative_to(path)]
            container_mount = max(parents, key=len)
            assert container_mount in sources, f'{host}: container backing mount {container_mount} omitted'

        # Follow protected binds into encrypted containers, then require coverage
        # of the filesystem containing the ciphertext. Direct external mounts
        # also require their own archive even when / is already selected.
        volumes = {value['mountPoint']: value['container'] for value in declaration['volumes'].values()}
        for protected in declaration['protected']:
            path, seen = Path(protected), set()
            while True:
                assert str(path) not in seen, f'{host}: cyclic protected mount routing'
                seen.add(str(path))
                parents = [mount for mount in declaration['mounts'] if path.is_relative_to(mount)]
                mount = max(parents, key=len)
                info = declaration['mounts'][mount]
                if mount in volumes:
                    path = Path(volumes[mount])
                elif info['fsType'] == 'none' and info['device'].startswith('/'):
                    path = Path(info['device']) / path.relative_to(mount)
                else:
                    assert mount in sources, f'{host}: protected path {protected} has unarchived backing mount {mount}'
                    break


def test_policy_helper_runs_without_site_packages_when_staged(tmp_path):
    for name in ['migration_policy.py', 'migration-policy.yml']:
        shutil.copyfile(ROOT / 'lx_administration/storage' / name, tmp_path / name)
    result = subprocess.run([sys.executable, '-S', '-c',
                             'import migration_policy as p; print(p.supported_hosts()); '
                             'print(p.writer("managed-secrets-setup.service"))'],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "gc-09" in result.stdout and "True" in result.stdout


def test_snapshot_stdin_transport_embeds_exact_policy_without_host_files(tmp_path):
    helper = (ROOT / 'lx_administration/storage/migration_policy.py').read_text()
    canonical = (ROOT / 'lx_administration/storage/migration-policy.yml').read_text()
    source = ('import sys, types\npolicy = types.ModuleType("migration_policy")\n'
              f'exec({helper!r}, policy.__dict__)\npolicy.POLICY_TEXT = {canonical!r}\n'
              'sys.modules["migration_policy"] = policy\n'
              'from migration_policy import snapshot_sources\nprint(snapshot_sources("gc-10")["data-raid01"])')
    result = subprocess.run([sys.executable, '-I', '-S', '-'], input=source,
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '/data/raid01'
