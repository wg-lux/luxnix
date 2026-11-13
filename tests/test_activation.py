"""Detached activation records and compatibility-bound recovery; no host changes."""
from contextlib import contextmanager
import hashlib
import json
import re
from pathlib import Path
import pytest
import yaml
from lx_administration import activation as a

REAL_LOCKED = a.locked


@pytest.fixture
def state(tmp_path, monkeypatch):
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    public = tmp_path / 'status'; public.mkdir(mode=0o755)
    monkeypatch.setattr(a, 'BASE', root)
    monkeypatch.setattr(a, 'PUBLIC', public)
    monkeypatch.setattr(a, 'private', lambda path: path.stat())
    @contextmanager
    def locked(*args, **kwargs):
        yield
    monkeypatch.setattr(a, 'locked', locked)
    current = tmp_path / 'current'; current.symlink_to('/nix/store/old')
    profile = tmp_path / 'profile'; profile.symlink_to('/nix/store/new')
    monkeypatch.setattr(a, 'CURRENT', current)
    monkeypatch.setattr(a, 'PROFILE', profile)
    value = {'id': 'a'*24, 'previous': '/nix/store/old', 'target': '/nix/store/new', 'action': 'switch', 'status': 'pending'}
    a.save(root / (value['id'] + '.json'), value)
    return value, current, profile


def test_matching_stateful_footprints_enable_automatic_compatibility(tmp_path):
    manifest = {'version':1,'activation':{'app':'hash'},'units':{'db':'hash'},'etc':{'postgresql':'hash'},'filesystems':'hash'}
    roots = [tmp_path / 'old', tmp_path / 'new']
    for root in roots:
        path = root / 'etc/luxnix/activation-compatibility.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(manifest))
    assert a.compatibility(*(str(p) for p in roots)) == 'identical-stateful-footprint'
    manifest['units']['db'] = 'changed'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='differ'):
        a.compatibility(*(str(p) for p in roots))


def test_compatibility_receipt_is_bound_to_closures_and_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(a, 'private', lambda path: None)
    evidence = tmp_path / 'evidence'; evidence.write_text('verified synthetic compatible database pair')
    receipt = tmp_path / 'receipt.json'
    value = {'version':1,'previous':'old','target':'new','assessor':'reviewer','safe_without_data_restore':True,'evidence':str(evidence),'sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}
    receipt.write_text(json.dumps(value))
    assert a.compatibility('old','new',receipt) == 'named-compatibility-assessment'
    with pytest.raises(ValueError, match='exact'):
        a.compatibility('other','new',receipt)
    evidence.write_text('changed')
    with pytest.raises(ValueError, match='changed'):
        a.compatibility('old','new',receipt)


def test_worker_waits_for_fresh_ack_and_repeated_ack_is_noop(state, monkeypatch):
    value, current, profile = state
    calls=[]
    def run(*args, **kwargs):
        calls.append(args)
        if args[0].endswith('/switch-to-configuration'):
            current.unlink(); current.symlink_to('/nix/store/new')
        return ''
    monkeypatch.setattr(a,'run',run)
    a.worker(value['id'])
    assert a.load(value['id'])[1]['status'] == 'awaiting-ack'
    a.acknowledge(value['id']); a.acknowledge(value['id'])
    assert a.load(value['id'])[1]['status'] == 'accepted'
    assert sum(args[:2] == ('systemctl','stop') for args in calls) == 1
    assert not any('reboot' in args or 'test' in args for args in calls)


def test_failed_activation_restores_only_bound_previous_generation(state, monkeypatch):
    value, current, profile = state
    calls=[]
    def run(*args, **kwargs):
        calls.append(args)
        if args[0] == '/nix/store/new/bin/switch-to-configuration':
            raise ValueError('failed new activation')
        if args[0] == 'nix-env':
            profile.unlink(); profile.symlink_to(args[-1])
        return ''
    monkeypatch.setattr(a,'run',run)
    with pytest.raises(ValueError, match='failed new'):
        a.worker(value['id'])
    assert a.load(value['id'])[1]['status'] == 'rolled-back'
    assert ('/nix/store/old/bin/switch-to-configuration','switch') in calls
    before=len(calls)
    a.recover(value['id'], stop_worker=False)
    assert len(calls) == before


def test_ack_rejects_wrong_active_generation(state):
    value, current, profile = state
    value['status']='awaiting-ack'; a.save(a.BASE/(value['id']+'.json'),value)
    with pytest.raises(ValueError, match='not completed'):
        a.acknowledge(value['id'])
    assert a.load(value['id'])[1]['status'] == 'awaiting-ack'


def test_watchdog_is_armed_before_worker_and_pending_retry_is_noop(state, monkeypatch, tmp_path):
    from types import SimpleNamespace
    value, current, profile = state
    (a.BASE / (value['id'] + '.json')).unlink()
    previous = '/nix/store/' + 'a' * 32 + '-nixos-system-old'
    target = '/nix/store/' + 'b' * 32 + '-nixos-system-new'
    monkeypatch.setattr(a, 'CURRENT', SimpleNamespace(resolve=lambda **k: Path(previous)))
    monkeypatch.setattr(a, 'retained_helper', lambda: tmp_path / 'helper.py')
    monkeypatch.setattr(a, 'compatibility', lambda *args: 'identical-stateful-footprint')
    monkeypatch.setattr(a.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=1))
    calls=[]
    monkeypatch.setattr(a,'run',lambda *args, **kwargs: calls.append(args))
    identifier=a.start(target,'switch')
    before=len(calls)
    assert a.start(target,'switch') == identifier
    assert len(calls) == before
    units=[args[1] for args in calls if args[0]=='systemd-run']
    assert units == ['--unit=luxnix-rollback-'+identifier,'--unit=luxnix-activate-'+identifier]
    assert sum(args[0]=='nix-store' for args in calls)==2


def _rollback_commands(state, calls):
    value, current, profile = state
    def run(*args, **kwargs):
        calls.append(args)
        if args[:2] == ('systemctl', 'stop'):
            raise ValueError('synthetic stop failure with private output withheld')
        if args[0] == 'nix-env':
            profile.unlink(); profile.symlink_to(args[-1])
        if args[0] == '/nix/store/old/bin/switch-to-configuration':
            current.unlink(); current.symlink_to('/nix/store/old')
        return ''
    return run


@pytest.mark.parametrize('show_code', [0, 1, 4])
def test_watchdog_rolls_back_when_worker_was_garbage_collected(state, monkeypatch, show_code):
    from types import SimpleNamespace
    value, current, profile = state
    calls = []
    monkeypatch.setattr(a, 'run', _rollback_commands(state, calls))
    probes = []
    def show(command, **kwargs):
        probes.append(command)
        return SimpleNamespace(returncode=show_code, stdout=(
            'LoadState=not-found\nActiveState=inactive\nMainPID=0\nControlPID=0\n'))
    monkeypatch.setattr(a.subprocess, 'run', show)
    a.recover(value['id'])
    assert a.load(value['id'])[1]['status'] == 'rolled-back'
    assert str(profile.resolve()) == str(current.resolve()) == '/nix/store/old'
    assert probes == [[
        'systemctl', 'show', 'luxnix-activate-' + value['id'] + '.service', '--all',
        '--property=LoadState', '--property=ActiveState', '--property=MainPID', '--property=ControlPID']]
    before = (list(calls), list(probes))
    a.recover(value['id'])
    assert (calls, probes) == before


@pytest.mark.parametrize('show_code,properties', [
    (1, ''),  # An unavailable system bus is not an absent unit.
    (1, 'LoadState=loaded\nActiveState=active\nMainPID=123\nControlPID=0\n'),
    (0, 'LoadState=not-found\nActiveState=inactive\nMainPID=123\nControlPID=0\n'),
    (0, 'LoadState=not-found\nActiveState=inactive\nMainPID=0\nControlPID=123\n'),
    (2, 'LoadState=not-found\nActiveState=inactive\nMainPID=0\nControlPID=0\n'),
    (0, 'LoadState=not-found\nActiveState=inactive\n'),
    (0, 'LoadState=not-found\nActiveState=inactive\nMainPID=0\nControlPID=0\nMainPID=123\n'),
])
def test_stop_failure_cannot_roll_back_a_live_or_unknown_worker(state, monkeypatch, show_code, properties):
    from types import SimpleNamespace
    value, current, profile = state
    calls = []
    monkeypatch.setattr(a, 'run', _rollback_commands(state, calls))
    monkeypatch.setattr(a.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=show_code, stdout=properties))
    with pytest.raises(ValueError, match='rollback refused'):
        a.recover(value['id'])
    assert a.load(value['id'])[1]['status'] == 'pending'
    assert str(profile.resolve()) == '/nix/store/new'
    assert not any(command[0] == 'nix-env' for command in calls)


@pytest.mark.parametrize('status', ['accepted', 'rolled-back'])
def test_terminal_recovery_never_requires_a_worker_unit(state, monkeypatch, status):
    value, _, _ = state
    value['status'] = status
    a.save(a.BASE / (value['id'] + '.json'), value)
    monkeypatch.setattr(a, 'run', lambda *args, **kwargs: pytest.fail('terminal record touched systemd'))
    a.recover(value['id'])
    assert a.load(value['id'])[1]['status'] == status


def test_successful_worker_stop_does_not_query_an_absent_unit(state, monkeypatch):
    value, _, _ = state
    calls = []
    rollback = _rollback_commands(state, calls)
    def run(*args, **kwargs):
        if args[:2] == ('systemctl', 'stop'):
            calls.append(args)
            return ''
        return rollback(*args, **kwargs)
    monkeypatch.setattr(a, 'run', run)
    monkeypatch.setattr(a.subprocess, 'run', lambda *args, **kwargs: pytest.fail('unexpected unit query'))
    a.recover(value['id'])
    assert a.load(value['id'])[1]['status'] == 'rolled-back'


def test_watchdog_serializes_worker_stop_and_rollback_under_actual_state_lock(state, monkeypatch):
    import subprocess
    import sys
    value, _, _ = state
    # Use the real file-lock protocol without requiring a root test process.
    monkeypatch.setattr(a, 'locked', REAL_LOCKED)
    monkeypatch.setattr(a.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(
        a, 'save', lambda path, record: path.write_text(json.dumps(record))
    )
    calls = []
    rollback = _rollback_commands(state, calls)
    def run(*args, **kwargs):
        # A separate would-be start/ack publisher cannot acquire the state lock
        # during worker termination or either rollback operation.
        result = subprocess.run([sys.executable, '-c',
            'import fcntl, sys; f = open(sys.argv[1], "a"); '
            'fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)',
            str(a.BASE / '.lock')], capture_output=True, text=True)
        assert result.returncode != 0
        assert 'BlockingIOError' in result.stderr
        if args[:2] == ('systemctl', 'stop'):
            calls.append(args)
            return ''
        return rollback(*args, **kwargs)
    monkeypatch.setattr(a, 'run', run)
    a.recover(value['id'])
    assert a.load(value['id'])[1]['status'] == 'rolled-back'
    # The lock is released after the complete rollback, permitting a later ack
    # to inspect the terminal record rather than racing an active worker.
    with a.locked():
        assert a.load(value['id'])[1]['status'] == 'rolled-back'


def test_missing_unit_confirmation_timeout_leaves_state_unchanged(state, monkeypatch):
    import subprocess
    value, _, profile = state
    calls = []
    monkeypatch.setattr(a, 'run', _rollback_commands(state, calls))
    def show(*args, **kwargs):
        raise subprocess.TimeoutExpired('systemctl show', kwargs['timeout'])
    monkeypatch.setattr(a.subprocess, 'run', show)
    with pytest.raises(subprocess.TimeoutExpired):
        a.recover(value['id'])
    assert a.load(value['id'])[1]['status'] == 'pending'
    assert str(profile.resolve()) == '/nix/store/new'
    assert not any(command[0] == 'nix-env' for command in calls)


def test_legacy_recovery_activation_tag_cannot_skip_gates_or_fresh_login():
    root = Path(__file__).parents[1]
    playbook = root / 'ansible/playbooks/storage-legacy-recovery.yml'
    tasks = yaml.safe_load(playbook.read_text())[0]['tasks']
    selected = [task for task in tasks if 'activate' in task.get('tags', [])]

    gate = selected[0]['ansible.builtin.assert']['that']
    assert {'release_build is defined', 'opened_mappings is defined'} <= set(gate)
    assert [task['name'] for task in selected[-3:]] == [
        'Close cached SSH transport',
        'Verify fresh SSH access',
        'Acknowledge the exact activation only after a fresh SSH login',
    ]


def test_storage_preflight_runs_candidate_helper_before_profile_publication(
    tmp_path, monkeypatch
):
    target = tmp_path / 'target'
    (target / 'etc/luxnix').mkdir(parents=True)
    (target / 'etc/luxnix/root-storage.json').write_text('{}')
    helper = target / 'sw/bin/luxnix-root-preflight'
    helper.parent.mkdir(parents=True)
    helper.write_text('#!/bin/sh\nexit 0\n')
    calls = []
    monkeypatch.setattr(a, 'run', lambda *args: calls.append(args))
    assert a.storage_preflight(str(target), 'boot') is True
    assert calls == [
        (str(helper), 'verify', '--system', str(target), '--action', 'boot')
    ]
    helper.unlink()
    with pytest.raises(ValueError, match='helper is missing'):
        a.storage_preflight(str(target), 'boot')


def test_unguarded_old_generation_cannot_be_used_for_encrypted_rollback(tmp_path):
    with pytest.raises(ValueError, match='independent recovery media'):
        a.storage_preflight(str(tmp_path), 'boot', required=True)


def test_worker_storage_rejection_never_changes_profile_or_arms_rollback(
    state, monkeypatch
):
    value, current, profile = state
    def reject(*args, **kwargs):
        raise ValueError('plaintext root cannot activate encrypted candidate')
    monkeypatch.setattr(a, 'storage_preflight', reject)
    monkeypatch.setattr(
        a, 'run',
        lambda *args, **kwargs: pytest.fail('rejected storage changed host state'),
    )
    with pytest.raises(ValueError, match='plaintext root'):
        a.worker(value['id'])
    assert a.load(value['id'])[1]['status'] == 'rejected'
    assert str(profile.resolve()) == '/nix/store/new'
    assert str(current.resolve()) == '/nix/store/old'
    a.recover(value['id'])


def test_recovery_storage_rejection_preserves_profile(state, monkeypatch):
    value, current, profile = state
    calls = []
    monkeypatch.setattr(a, 'run', lambda *args, **kwargs: calls.append(args))
    def reject(*args, **kwargs):
        raise ValueError('previous root no longer matches physical storage')
    monkeypatch.setattr(a, 'storage_preflight', reject)
    with pytest.raises(ValueError, match='physical storage'):
        a.recover(value['id'])
    assert a.load(value['id'])[1]['status'] == 'recovering'
    assert not any(args[0] == 'nix-env' for args in calls)
    assert str(profile.resolve()) == '/nix/store/new'


@pytest.mark.parametrize('missing', ['previous', 'target'])
def test_guarded_pair_requires_contract_on_both_sides_before_scheduling(
    state, monkeypatch, tmp_path, missing
):
    value, current, profile = state
    previous, target = [tmp_path / name for name in ('previous', 'target')]
    for candidate in (previous, target):
        candidate.mkdir()
        if candidate.name != missing:
            contract = candidate / 'etc/luxnix/root-storage.json'
            contract.parent.mkdir(parents=True)
            contract.write_text('{}')
            helper = candidate / 'sw/bin/luxnix-root-preflight'
            helper.parent.mkdir(parents=True)
            helper.write_text('#!/bin/sh\nexit 0\n')
    current.unlink()
    current.symlink_to(previous)
    for path in a.BASE.glob('*.json'):
        path.unlink()
    monkeypatch.setattr(a, 'CLOSURE', re.compile('.*'))
    monkeypatch.setattr(a, 'retained_helper', lambda: Path('/retained/helper'))
    calls = []
    monkeypatch.setattr(a, 'run', lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError, match='no storage admission contract'):
        a.start(str(target), 'boot')
    assert not list(a.BASE.glob('*.json'))
    assert not any(args[0] in {'nix-env', 'systemd-run', 'nix-store'} for args in calls)
    assert str(profile.resolve()) == '/nix/store/new'


@pytest.mark.parametrize('refused', [False, True])
def test_guard_verify_cli_never_mutates_profile_or_consumes_override(
    tmp_path, monkeypatch, refused
):
    from lx_administration.storage import root_guard

    spec = tmp_path / 'spec.json'
    spec.write_text(json.dumps({'host': 'synthetic'}))
    monkeypatch.setattr(root_guard, 'observe', lambda *args, **kwargs: {})
    decisions = []

    def assess(*args, **kwargs):
        decisions.append(kwargs)
        return [root_guard.Finding('test', 'synthetic refusal')] if refused else []

    monkeypatch.setattr(root_guard, 'assess', assess)
    for name in ('withdraw', 'consume_override'):
        monkeypatch.setattr(
            root_guard, name,
            lambda *args, **kwargs: pytest.fail('verify must not mutate state'),
        )
    with pytest.raises(SystemExit) as result:
        root_guard.main([
            'verify', '--spec', str(spec), '--system', '/nix/store/synthetic',
            '--action', 'boot',
        ])
    assert result.value.code == int(refused)
    assert decisions and decisions[0]['action'] == 'boot'
