"""Detached activation records and compatibility-bound recovery; no host changes."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import pytest
from lx_administration import activation as a


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
