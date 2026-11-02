"""Backup refusal, authenticated recovery and snapshot failure cleanup contracts."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from lx_administration.storage import migration_backup as backup
from lx_administration.storage import snapshot


def test_snapshot_scope_rejects_another_host_or_path():
    item = {'source': '/', 'name': 'root',
            'snapshot': '/var/lib/luxnix-migration-snapshots/reviewed-01/root'}
    backup.validate_snapshot('gc-09', 'reviewed-01', item)
    for host, identifier, change in [('gc-02', 'reviewed-01', {}),
                                     ('gc-09', '../outside', {}),
                                     ('gc-09', 'reviewed-01', {'snapshot': '/etc/secrets'}),
                                     ('gc-09', 'reviewed-01', {'source': '/data/raid01'})]:
        with pytest.raises(ValueError):
            backup.validate_snapshot(host, identifier, item | change)


@pytest.mark.skipif(not shutil.which('age-keygen'), reason='age required')
def test_real_age_archive_authentication_and_wrong_digest(tmp_path):
    identity = tmp_path / 'identity'
    subprocess.run(['age-keygen', '-o', str(identity)], check=True, capture_output=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
    data = b'existing synthetic backup content' * 100
    archive = tmp_path / 'backup.age'
    archive.write_bytes(subprocess.run(['age', '-r', recipient], input=data,
                                      capture_output=True, check=True).stdout)
    digest = hashlib.sha256(data).hexdigest()
    backup.verify_archive(archive, identity, digest)
    streamed = tmp_path / 'streamed.age'
    receipt = backup.transfer(None, ['printf', 'synthetic-stream'], streamed, recipient, identity)
    assert receipt['authenticated'] and not receipt['application_restore_tested']
    assert not streamed.with_suffix('.age.partial').exists()
    backup.verify_archive(streamed, identity, hashlib.sha256(b'synthetic-stream').hexdigest())
    with pytest.raises(ValueError):
        backup.verify_archive(archive, identity, '0' * 64)
    pending = tmp_path / 'host-local.age'
    local = backup.transfer(None, ['printf', 'host-local-synthetic'], pending, recipient, None)
    assert not local['authenticated'] and not pending.exists()
    encrypted = pending.with_suffix('.age.unverified')
    fd = os.memfd_create('test-recovery')
    try:
        os.write(fd, identity.read_bytes())
        os.lseek(fd, 0, os.SEEK_SET)
        backup.verify_archive(encrypted, Path(f'/proc/self/fd/{fd}'),
                              local['sha256_compressed_stream'], pass_fds=(fd,))
    finally:
        os.close(fd)
    with pytest.raises(ValueError, match='refusing replacement'):
        backup.transfer(None, ['printf', 'replacement'], pending, recipient, None)
    archive.write_bytes(archive.read_bytes()[:-1])
    with pytest.raises(ValueError):
        backup.verify_archive(archive, identity, digest)


def test_existing_backup_never_replaced(tmp_path):
    target = tmp_path / 'backup.age'
    target.write_bytes(b'existing')
    with pytest.raises(ValueError, match='refusing replacement'):
        backup.transfer(None, [], target, 'unused', tmp_path / 'identity')
    assert target.read_bytes() == b'existing'


@pytest.fixture
def snapshot_host(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(snapshot, 'BASE', tmp_path / 'snapshots')
    monkeypatch.setattr(snapshot.socket, 'gethostname', lambda: 'gc-09')
    calls = []
    state = {'postgresql.service': 'active', 'lx-annotate.service': 'inactive',
             'nginx.service': 'inactive'}
    masks = {'nginx.service'}
    frozen = set()
    identities = {}
    failures = {}
    def mount(path, optional=False):
        return {'source': '/dev/mapper/root', 'fstype': 'btrfs',
                'uuid': failures.get('mount_uuid', 'filesystem'), 'fsroot': path}
    def subvolume(path):
        path = str(path)
        return identities.get(path, {'uuid': 'source-' + path, 'parent_uuid': '-'})
    def run(*args, **kwargs):
        calls.append(args)
        if args[:2] == ('systemctl', 'list-units'):
            return '\n'.join(u + ' loaded ' + s for u, s in state.items()) + '\nsshd.service loaded active'
        if args[:2] == ('systemctl', 'show'):
            return ('masked' if args[2] in masks else 'loaded') if 'LoadState' in args else state[args[2]]
        if args[:2] == ('systemctl', 'mask'):
            masks.add(args[-1])
        if args[:2] == ('systemctl', 'unmask'):
            masks.discard(args[-1])
        if args[:2] == ('systemctl', 'stop'):
            for unit in args[2:]:
                state[unit] = 'inactive'
        if args[:2] == ('systemctl', 'start'):
            if failures.get('restart'):
                raise RuntimeError('synthetic restart failure')
            state[args[-1]] = 'active'
        if args[:2] == ('fsfreeze', '--freeze'):
            frozen.add(args[-1])
        if args[:3] == ('btrfs', 'subvolume', 'snapshot'):
            if failures.get('snapshot'):
                raise RuntimeError('synthetic snapshot failure')
            if failures.get('signal'):
                snapshot.interrupted(15, None)
            target = Path(args[-1])
            target.mkdir()
            identities[str(target)] = {'uuid': 'snapshot-' + str(target), 'parent_uuid': subvolume(args[-2])['uuid']}
        if args[:3] == ('btrfs', 'property', 'get'):
            return 'ro=false' if failures.get('writable') else 'ro=true'
        return ''
    def thaw(path):
        calls.append(('thaw', path))
        if failures.get('thaw'):
            raise RuntimeError('synthetic thaw failure')
        frozen.discard(path)
    monkeypatch.setattr(snapshot, 'mount_identity', mount)
    monkeypatch.setattr(snapshot, 'subvolume', subvolume)
    monkeypatch.setattr(snapshot, 'run', run)
    monkeypatch.setattr(snapshot, 'thaw', thaw)
    return SimpleNamespace(calls=calls, state=state, masks=masks, frozen=frozen,
                           identities=identities, failures=failures,
                           plan=lambda name='reviewed-01': snapshot.BASE / name / 'plan.json',
                           read=lambda name='reviewed-01': json.loads((snapshot.BASE / name / 'plan.json').read_text()))


def test_snapshot_failure_unfreezes_and_restores_only_previous_writers(snapshot_host):
    host = snapshot_host
    host.failures['snapshot'] = True
    with pytest.raises(RuntimeError, match='synthetic snapshot failure'):
        snapshot.snapshot('gc-09', 'reviewed-01')
    assert host.frozen == set()
    assert host.state['postgresql.service'] == 'active'
    assert host.state['lx-annotate.service'] == 'inactive'
    assert host.masks == {'nginx.service'}
    assert all('sshd.service' not in args for args in host.calls)
    assert host.read()['complete'] is False
    assert host.read()['state'] == 'recovered'


def test_completed_snapshot_retry_checks_identity_without_stopping_writers(snapshot_host):
    host = snapshot_host
    first = snapshot.snapshot('gc-09', 'reviewed-01')
    assert first['complete'] and first['changed']
    assert len(first['snapshots']) == 5
    before = host.plan().read_bytes()
    host.calls.clear()
    repeated = snapshot.snapshot('gc-09', 'reviewed-01')
    assert not repeated['changed']
    assert host.plan().read_bytes() == before
    assert not any(args[0] in {'systemctl', 'fsfreeze'} for args in host.calls)
    host.failures['writable'] = True
    with pytest.raises(ValueError, match='not read-only'):
        snapshot.snapshot('gc-09', 'reviewed-01')


def test_snapshot_retry_rejects_substituted_snapshot_or_source(snapshot_host):
    host = snapshot_host
    report = snapshot.snapshot('gc-09', 'reviewed-01')
    target = report['snapshots'][0]['snapshot']
    host.identities[target] = {'uuid': 'replacement', 'parent_uuid': 'source-/'}
    with pytest.raises(ValueError, match='identity changed'):
        snapshot.snapshot('gc-09', 'reviewed-01')
    host.failures['mount_uuid'] = 'another-filesystem'
    with pytest.raises(ValueError, match='Source changed'):
        snapshot.snapshot('gc-09', 'reviewed-01', 'recover')


def test_thaw_failure_keeps_writers_masked_until_explicit_recovery(snapshot_host):
    host = snapshot_host
    host.failures.update(snapshot=True, thaw=True)
    with pytest.raises(RuntimeError, match='Operator recovery required'):
        snapshot.snapshot('gc-09', 'reviewed-01')
    assert host.state['postgresql.service'] == 'inactive'
    assert host.masks == {'nginx.service', 'postgresql.service', 'lx-annotate.service'}
    assert host.read()['state'] == 'recovery_required'
    with pytest.raises(ValueError, match='Incomplete run'):
        snapshot.snapshot('gc-09', 'reviewed-01')
    with pytest.raises(ValueError, match='Interrupted run'):
        snapshot.snapshot('gc-09', 'reviewed-02')
    host.failures.clear()
    assert snapshot.snapshot('gc-09', 'reviewed-01', 'recover')['changed']
    assert host.frozen == set() and host.masks == {'nginx.service'}
    assert host.state['postgresql.service'] == 'active'
    assert not snapshot.snapshot('gc-09', 'reviewed-01', 'recover')['changed']
    with pytest.raises(ValueError, match='new snapshot identifier'):
        snapshot.snapshot('gc-09', 'reviewed-01')
    assert snapshot.snapshot('gc-09', 'reviewed-02')['complete']


def test_restart_failure_is_retained_for_explicit_retry(snapshot_host):
    host = snapshot_host
    host.failures['restart'] = True
    with pytest.raises(RuntimeError, match='restart postgresql'):
        snapshot.snapshot('gc-09', 'reviewed-01')
    assert host.read()['pending_restart'] == ['postgresql.service']
    assert host.read()['complete'] is False
    host.failures.clear()
    assert snapshot.snapshot('gc-09', 'reviewed-01', 'recover')['state'] == 'recovered'
    assert host.state['lx-annotate.service'] == 'inactive'


def test_catchable_signal_restores_writers_without_claiming_completion(snapshot_host):
    host = snapshot_host
    host.failures['signal'] = True
    with pytest.raises(RuntimeError, match='interrupted by signal'):
        snapshot.snapshot('gc-09', 'reviewed-01')
    assert host.frozen == set()
    assert host.state['postgresql.service'] == 'active'
    assert host.read()['state'] == 'recovered'
    assert not host.read()['complete']


def test_host_lock_serializes_different_snapshot_identifiers(snapshot_host):
    import sys
    with snapshot.operation('snapshot'):
        # Check the actual cross-process lock directly, independent of host name.
        result = subprocess.run([sys.executable, '-c',
            "from pathlib import Path; from lx_administration.storage import snapshot; "
            "import sys; snapshot.BASE=Path(sys.argv[1]); "
            "snapshot.operation('snapshot').__enter__()",
            str(snapshot.BASE)], capture_output=True, text=True)
        assert result.returncode != 0
        assert 'Another snapshot operation is running' in result.stderr


def test_journal_intents_survive_uncatchable_worker_exit(snapshot_host):
    import json
    import sys
    host = snapshot_host
    # Start from a valid journal then model a crash after intent publication but
    # before the operation acknowledges thaw/mask changes. No finally can run.
    snapshot.snapshot('gc-09', 'reviewed-01')
    report = host.read()
    report.update(state='in_progress', complete=False, pending_freezes=list(snapshot.INNER),
                  pending_masks=['postgresql.service'], pending_restart=['postgresql.service'])
    result = subprocess.run([sys.executable, '-c',
        'import json, os, sys, signal; from pathlib import Path; '
        'from lx_administration.storage.snapshot import save; '
        'save(Path(sys.argv[1]), json.loads(sys.argv[2])); os.kill(os.getpid(), signal.SIGKILL)',
        str(host.plan()), json.dumps(report)])
    assert result.returncode == -9
    with pytest.raises(ValueError, match='Interrupted run'):
        snapshot.snapshot('gc-09', 'reviewed-02')
    host.state['postgresql.service'] = 'inactive'
    host.masks.add('postgresql.service')
    recovered = snapshot.automatic_recovery('gc-09', 'reviewed-01')
    assert recovered['state'] == 'recovered' and not recovered['complete']
    assert len(recovered['snapshots']) == 5
    assert host.state['postgresql.service'] == 'active'


def test_automatic_recovery_retries_transient_thaw_without_new_snapshot(snapshot_host, monkeypatch):
    host = snapshot_host
    host.failures.update(snapshot=True, thaw=True)
    with pytest.raises(RuntimeError):
        snapshot.snapshot('gc-09', 'reviewed-01')
    sleeps = []
    def retry_delay(seconds):
        sleeps.append(seconds)
        host.failures.clear()
    monkeypatch.setattr(snapshot.time, 'sleep', retry_delay)
    host.calls.clear()
    result = snapshot.automatic_recovery('gc-09', 'reviewed-01')
    assert result['state'] == 'recovered' and not result['complete']
    assert sleeps == [5]
    assert host.frozen == set()
    assert not any(args[:3] == ('btrfs', 'subvolume', 'snapshot') for args in host.calls)


def test_automatic_recovery_is_bounded_and_never_starts_after_bad_thaw(snapshot_host, monkeypatch):
    host = snapshot_host
    host.failures.update(snapshot=True, thaw=True)
    with pytest.raises(RuntimeError):
        snapshot.snapshot('gc-09', 'reviewed-01')
    sleeps = []
    monkeypatch.setattr(snapshot.time, 'sleep', sleeps.append)
    host.calls.clear()
    with pytest.raises(RuntimeError, match='unfreeze'):
        snapshot.automatic_recovery('gc-09', 'reviewed-01')
    assert sleeps == [5, 5]
    assert not any(args[:2] == ('systemctl', 'start') for args in host.calls)
    assert host.read()['pending_freezes']


def test_sealed_openbao_keeps_writers_masked_until_semantic_recovery(snapshot_host, monkeypatch):
    host = snapshot_host
    host.state['openbao-local.service'] = 'active'
    monkeypatch.setattr(snapshot, 'openbao_ready', lambda: (_ for _ in ()).throw(ValueError('sealed')))
    with pytest.raises(RuntimeError, match='unsealed active local OpenBao'):
        snapshot.snapshot('gc-09', 'reviewed-01')
    assert host.state['openbao-local.service'] == 'active'
    assert host.state['postgresql.service'] == 'inactive'
    assert 'postgresql.service' in host.masks
    assert 'openbao-local.service' in host.read()['pending_restart']
    monkeypatch.setattr(snapshot, 'openbao_ready', lambda: None)
    assert snapshot.automatic_recovery('gc-09', 'reviewed-01')['state'] == 'recovered'
    assert host.state['postgresql.service'] == 'active'


def test_supervision_is_installed_before_snapshot_exec():
    import yaml
    play = yaml.safe_load((Path(__file__).resolve().parents[1] / 'ansible/playbooks/storage-migration-snapshot.yml').read_text())[0]
    task = next(t for t in play['tasks'] if t['name'].startswith('Run supervised'))
    argv = task['ansible.builtin.command']['argv']
    assert argv[0] == 'systemd-run'
    cleanup = next(a for a in argv if a.startswith('--property=ExecStopPost='))
    assert cleanup.endswith(' recover-auto')
    assert argv.index(cleanup) < argv.index('/run/current-system/sw/bin/python3')
    assert '--property=KillMode=control-group' in argv
    assert '--property=RuntimeMaxSec=1800' in argv
    assert '--property=TimeoutStopSec=600' in argv


@pytest.mark.parametrize('actual_uuid,requested_uuid', [('wrong-disk', 'backup'), ('source', 'source')])
def test_host_local_backup_rejects_wrong_or_source_filesystem_before_writes(tmp_path, monkeypatch, actual_uuid, requested_uuid):
    import json
    import sys
    from lx_administration.storage import migration_archive as archive
    monkeypatch.setattr(archive.socket, 'gethostname', lambda: 'gc-09')
    monkeypatch.setattr(archive.os, 'umask', lambda mode: 0)
    monkeypatch.setattr(archive.resource, 'setrlimit', lambda *args: None)
    monkeypatch.setattr(Path, 'is_mount', lambda self: True)
    monkeypatch.setattr(archive.subprocess, 'check_output', lambda *a, **k:
                        json.dumps({'filesystems': [{'uuid': actual_uuid}]}))
    plan = {'complete': True, 'host': 'gc-09', 'identifier': 'reviewed-01',
            'mounts': {'/': {'uuid': 'source'}}}
    monkeypatch.setattr(Path, 'read_text', lambda *a, **k: json.dumps(plan))
    monkeypatch.setattr(sys, 'argv', ['archive', '--snapshot-id', 'reviewed-01',
                        '--destination', str(tmp_path), '--destination-uuid', requested_uuid,
                        '--recipient', 'synthetic-public-recipient'])
    with pytest.raises(SystemExit) as failure:
        archive.local_main()
    assert failure.value.code == 2
    assert list(tmp_path.iterdir()) == []
