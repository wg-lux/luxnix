"""Guided provisioning delegates to the controller and never applies unconfirmed."""
import json
from types import SimpleNamespace

import pytest

from lx_administration.storage import provision_setup as setup

STORAGE = {'layout': 'legacy-containers', 'unlockMethod': 'passphrase',
           'volumes': {'app': {'container': '/data/app.luks', 'luksUUID': None},
                       'bound': {'container': None, 'luksUUID': None}}}
UUID = '11111111-2222-3333-4444-555555555555'


class FakeEnv:
    def __init__(self, storage=STORAGE, exists=False, apply_ok=True):
        self.storage = storage
        self.exists = exists
        self.apply_ok = apply_ok
        self.calls = []

    def nix_json(self, attribute, apply=None):
        return ['gc-10', 'gs-01', 'gc-02'] if attribute == 'nixosConfigurations' else self.storage

    def inventory_hosts(self):
        return {'gc-10': '10.0.0.10', 'gs-01': '10.0.0.1', 'gc-02': '10.0.0.2'}

    def hostname(self):
        return 'gc-02'

    def connectivity(self, host):
        self.calls.append(('connect', host))
        return True, []

    def sudo_ready(self, choices, address):
        return None

    def refresh_local_sudo(self):
        return True

    def admin_vault_problem(self, *args):
        return None

    def controller(self, argv):
        self.calls.append(('controller', argv))
        apply = '--apply' in argv
        if apply and not self.apply_ok:
            return None
        summary = {'host': 'gc-10', 'volume': 'app', 'container': '/data/app.luks',
                   'recovery_host': 'gs-01', 'backend': 'passphrase', 'action': 'provision',
                   'machine_id': 'a' * 32, 'exists': self.exists, 'luks_uuid': UUID if self.exists else None}
        return dict(summary, luks_uuid=UUID, escrow_verified=True,
                    primary_escrow='/p', emergency_export='gs-01:/e') if apply else summary


def console(answers):
    queue = list(answers)
    output = []
    return setup.Console(read=lambda prompt: queue.pop(0), write=output.append), output


def preset(**values):
    base = dict(host=None, volume=None, recovery_host=None, backend=None, sudo_password_file=None)
    return SimpleNamespace(**dict(base, **values))


def go(env, answers, tmp_path, **values):
    con, output = console(answers)
    result = setup.run(con, env, setup.State(tmp_path / 'state'), preset(**values),
                       tmp_path / 'vault', tmp_path / 'key')
    return result, output


def applied(env):
    return [argv for kind, argv in env.calls if kind == 'controller' and '--apply' in argv]


@pytest.mark.parametrize("layout", ["legacy-containers", "unencrypted-root"])
def test_guided_apply_uses_exact_controller_arguments_and_saves_private_state(tmp_path, layout):
    env = FakeEnv(storage=dict(STORAGE, layout=layout))
    # host, backend (default), typed confirmation; gs-01 is the only valid recovery host
    result, _ = go(env, ['gc-10', '', 'gc-10'], tmp_path)
    assert result['escrow_verified']
    assert applied(env) == [['provision', '--host', 'gc-10', '--volume', 'app', '--recovery-host',
                             'gs-01', '--backend', 'passphrase', '--apply']]
    state = tmp_path / 'state' / 'gc-10--app.json'
    assert state.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / 'state').stat().st_mode & 0o777 == 0o700
    saved = json.loads(state.read_text())
    assert saved['completed']['luks_uuid'] == UUID and saved['apply_started']
    assert 'recovery_passphrase' not in state.read_text()


def test_wrong_confirmation_never_applies(tmp_path):
    env = FakeEnv()
    with pytest.raises(setup.SetupStopped, match='Not confirmed'):
        go(env, ['gc-10', '', 'gc-1'], tmp_path)
    assert applied(env) == []


def test_interrupted_apply_preserves_resume_state_and_reports_possible_changes(tmp_path):
    env = FakeEnv()
    original = env.controller
    def interrupt(argv):
        if '--apply' in argv:
            raise KeyboardInterrupt
        return original(argv)
    env.controller = interrupt
    with pytest.raises(setup.SetupStopped, match='may have created recovery copies'):
        go(env, ['gc-10', '', 'gc-10'], tmp_path)
    saved = json.loads((tmp_path / 'state/gc-10--app.json').read_text())
    assert saved['apply_started'] and not saved['completed']


def test_boot_luks_hosts_are_refused_before_any_connection(tmp_path):
    env = FakeEnv(storage=dict(STORAGE, layout='boot-luks'))
    with pytest.raises(setup.SetupStopped, match='boot-storage-migration'):
        go(env, ['gc-10'], tmp_path)
    assert env.calls == []


def test_recovery_host_cannot_be_target_or_controller(tmp_path):
    with pytest.raises(setup.SetupStopped, match='another inventory host'):
        go(FakeEnv(), [''], tmp_path, host='gc-10', recovery_host='gc-02')


def test_passphrase_backend_rejected_under_tpm_policy(tmp_path):
    env = FakeEnv(storage=dict(STORAGE, unlockMethod='tpm2'))
    with pytest.raises(setup.SetupStopped, match='not allowed'):
        go(env, [], tmp_path, host='gc-10', backend='passphrase')


def test_preview_mismatch_stops(tmp_path):
    env = FakeEnv()
    original = env.controller
    env.controller = lambda argv: dict(original(argv), container='/other.luks')
    with pytest.raises(setup.SetupStopped, match='does not match'):
        go(env, ['gc-10', ''], tmp_path)
    assert applied(env) == []


def test_unknown_existing_container_is_protected(tmp_path):
    env = FakeEnv(exists=True)
    with pytest.raises(setup.SetupStopped, match='protect'):
        go(env, ['gc-10', '', ''], tmp_path)
    assert applied(env) == []


def test_rerun_reuses_answers_and_only_reverifies_completed_volume(tmp_path):
    go(FakeEnv(), ['gc-10', '', 'gc-10'], tmp_path)
    env = FakeEnv(exists=True)
    # host, reuse saved answers (default yes), typed confirmation; no existing-container question
    result, output = go(env, ['gc-10', '', 'gc-10'], tmp_path)
    assert result['luks_uuid'] == UUID
    assert any('only re-verifies' in line for line in output)
    assert len(applied(env)) == 1


def test_failed_apply_records_resume_point(tmp_path):
    env = FakeEnv(apply_ok=False)
    with pytest.raises(setup.SetupStopped, match='resumes safely'):
        go(env, ['gc-10', '', 'gc-10'], tmp_path)
    saved = json.loads((tmp_path / 'state' / 'gc-10--app.json').read_text())
    assert saved['apply_started'] and not saved['completed']


def test_concurrent_runs_are_refused(tmp_path):
    state = setup.State(tmp_path / 'state')
    held = state.lock('gc-10', 'app')
    try:
        with pytest.raises(setup.SetupStopped, match='already running'):
            state.lock('gc-10', 'app')
    finally:
        held.close()
