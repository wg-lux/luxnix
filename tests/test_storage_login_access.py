"""Exercise real seal cryptography and the ordered, fail-closed storage lifecycle."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from lx_administration.storage import openbao_local
from lx_administration import secret_storage

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('storage_login_access', ROOT / 'lx_administration/storage/login_access.py')
access = importlib.util.module_from_spec(spec)
# The deployed package deliberately contains these three standalone modules.
with pytest.MonkeyPatch.context() as patch:
    patch.setitem(sys.modules, 'openbao_local', openbao_local)
    patch.setitem(sys.modules, 'secret_storage', secret_storage)
    spec.loader.exec_module(access)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(access, 'STATE', tmp_path / 'accounts')
    monkeypatch.setattr(access, 'GATE', tmp_path / 'unlocked')
    monkeypatch.setattr(openbao_local, 'SEAL_WRAP', tmp_path / 'canonical.json')
    monkeypatch.setattr(openbao_local, 'SEAL_RUNTIME', tmp_path / 'seal.key')
    # Keep actual crypto, file permissions and validation; redirect defaults
    # captured by the original function definitions to disposable fixtures.
    stage = openbao_local.stage_verified_seal
    verify = openbao_local.verify_staged_seal
    monkeypatch.setattr(openbao_local, 'stage_verified_seal', lambda record, key: stage(record, key, tmp_path / 'seal.key'))
    monkeypatch.setattr(openbao_local, 'verify_staged_seal', lambda: verify(tmp_path / 'canonical.json', tmp_path / 'seal.key'))
    # CI may not run as root: still test privacy without requiring chown.
    monkeypatch.setattr(openbao_local, 'read_private', lambda p: p.read_bytes())
    key = bytes(range(32))
    canonical = openbao_local.wrap_seal_key(key, b'independent-recovery-password')
    (tmp_path / 'canonical.json').write_text(json.dumps(canonical))
    config = {'users': ['admin', 'client-user'], 'autoEnroll': True,
              'mounts': ['volume.mount', 'bind.mount'],
              'mountsReverse': ['bind.mount', 'volume.mount'],
              'volumes': [{'device': str(tmp_path / 'mapper')}],
              'startup': ['web.service'], 'consumers': ['web.service', 'postgresql.service'],
              'triggers': ['worker.timer'], 'startupTriggers': ['worker.timer']}
    calls = []
    monkeypatch.setattr(access, 'run', lambda *args: calls.append(args))
    return config, key, canonical, calls


def test_two_login_passwords_wrap_same_seal_without_storing_passwords(setup):
    config, key, canonical, _ = setup
    openbao_local.stage_verified_seal(canonical, key)
    for user in config['users']:
        password = (user + '-private-login-password').encode()
        access.unlock_key(config, user, password, enroll=True)
        record = access.STATE / (user + '.json')
        assert password not in record.read_bytes()
        assert record.stat().st_mode & 0o777 == 0o600
        assert openbao_local.unwrap_seal_key(json.loads(record.read_text()), password) == key
    assert (access.STATE / 'admin.json').read_bytes() != (access.STATE / 'client-user.json').read_bytes()


@pytest.mark.parametrize('user', ['root', '../admin', 'unknown', None])
def test_unknown_accounts_cannot_enroll_or_unlock(setup, user):
    with pytest.raises(ValueError):
        access.unlock_key(setup[0], user, b'private-password', enroll=True)
    assert not access.GATE.exists()


def test_first_login_requires_previously_authenticated_seal(setup):
    with pytest.raises(FileNotFoundError):
        access.unlock_key(setup[0], 'admin', b'private-password', enroll=True)
    assert not access.STATE.exists()


def test_wrong_password_never_starts_services(setup):
    config, key, canonical, calls = setup
    openbao_local.stage_verified_seal(canonical, key)
    access.unlock_key(config, 'admin', b'correct-password', enroll=True)
    access.GATE.unlink(missing_ok=True)
    with pytest.raises(ValueError, match='wrong-passphrase'):
        access.unlock(config, 'admin', b'incorrect-password')
    assert not calls and not access.GATE.exists()


def test_unlock_orders_bao_mounts_services_and_triggers(setup):
    config, key, canonical, calls = setup
    openbao_local.stage_verified_seal(canonical, key)
    access.unlock(config, 'admin', b'correct-password', enroll=True)
    assert calls == [('systemctl', 'start', 'openbao-local.service'),
                     ('systemctl', 'start', 'volume.mount', 'bind.mount'),
                     ('systemctl', 'start', 'web.service'),
                     ('systemctl', 'start', 'worker.timer')]


def test_lock_closes_mappings_only_after_consumers_and_mounts(setup):
    config, key, canonical, calls = setup
    Path(config['volumes'][0]['device']).touch()
    openbao_local.stage_verified_seal(canonical, key)
    access.GATE.touch()
    access.lock(config)
    assert calls == [('systemctl', 'stop', 'worker.timer'),
                     ('systemctl', 'stop', 'web.service', 'postgresql.service'),
                     ('systemctl', 'stop', 'bind.mount'),
                     ('systemctl', 'stop', 'volume.mount'),
                     ('cryptsetup', 'close', config['volumes'][0]['device']),
                     ('systemctl', 'stop', 'openbao-local.service', 'openbao-local-seal-key.service')]
    assert not access.GATE.exists() and not openbao_local.SEAL_RUNTIME.exists()


def test_busy_mount_preserves_key_and_reports_incomplete_lock(setup, monkeypatch):
    config, key, canonical, calls = setup
    openbao_local.stage_verified_seal(canonical, key)
    access.GATE.touch()
    def fail(*args):
        calls.append(args)
        if args[-1] == 'bind.mount':
            raise subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(access, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        access.lock(config)
    assert not access.GATE.exists()
    assert openbao_local.SEAL_RUNTIME.exists()
    assert all(args[0] != 'cryptsetup' for args in calls)


def test_failed_start_rolls_back_through_lock(setup, monkeypatch):
    config, key, canonical, calls = setup
    openbao_local.stage_verified_seal(canonical, key)
    def fail(*args):
        calls.append(args)
        if args == ('systemctl', 'start', 'web.service'):
            raise subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(access, 'run', fail)
    with pytest.raises(ValueError, match='locked again'):
        access.unlock(config, 'admin', b'correct-password', enroll=True)
    assert not access.GATE.exists() and not openbao_local.SEAL_RUNTIME.exists()


def test_real_host_login_profile_and_private_mount_dependencies():
    expression = r'''
      let f = builtins.getFlake "git+file:///home/admin/luxnix";
          lib = f.inputs.nixpkgs.lib;
          c = (f.nixosConfigurations.gc-10.extendModules { modules = [{
            luxnix.storage.operatorUnlocked.layout = "legacy-containers";
            luxnix.storage.operatorUnlocked.unlockMethod = lib.mkForce "local-openbao";
          }]; }).config;
      in {
        enabled = c.luxnix.storage.loginAccess.enable;
        users = c.luxnix.storage.loginAccess.users;
        pam = c.security.pam.services.login.text;
        sddm = c.security.pam.services.sddm.text;
        before = c.systemd.services.openbao-local-seal-key.before;
        boot = c.systemd.services.openbao-local.wantedBy;
        guard = c.systemd.services.lx-annotate.unitConfig.ConditionPathExists;
        private = c.systemd.services.luxnix-storage-permissions-luxnix-secrets.script;
        binds = c.fileSystems."/etc/secrets".options;
        hidden = c.fileSystems."/var/lib/luxnix-secrets".options;
      }
    '''.replace('git+file:///home/admin/luxnix', 'git+file://' + str(ROOT))
    data = json.loads(subprocess.check_output(['nix', 'eval', '--impure', '--json', '--expr', expression], cwd=ROOT))
    assert data['enabled'] and data['users'] == ['admin', 'client-user']
    assert data['pam'].index('# luxnix-storage (order', data['pam'].index('# Authentication')) < data['pam'].index('# unix (order', data['pam'].index('# Authentication'))
    assert 'auth substack login' in data['sddm']
    assert 'session include login' in data['sddm']
    assert data['before'] == data['boot'] == []
    assert '/run/luxnix-storage-access/unlocked' in data['guard']
    assert 'chmod 0700 /var/lib/luxnix-secrets' in data['private']
    assert 'x-systemd.requires=luxnix-storage-permissions-luxnix-secrets.service' in data['binds']
    assert 'x-gvfs-hide' in data['hidden']


def test_manual_trigger_is_stopped_but_not_started_automatically(setup):
    config, key, canonical, calls = setup
    config['startupTriggers'] = []
    openbao_local.stage_verified_seal(canonical, key)
    access.unlock(config, 'admin', b'correct-password', enroll=True)
    assert ('systemctl', 'start', 'worker.timer') not in calls
    access.lock(config)
    assert ('systemctl', 'stop', 'worker.timer') in calls
