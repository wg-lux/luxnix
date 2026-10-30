"""Recovery custody uses real Ansible encryption and disposable synthetic data."""
import json
from pathlib import Path
import secrets
import subprocess
import sys
from types import SimpleNamespace
import uuid

import pytest

from lx_administration.models.vault import secret
from lx_administration.storage import provision


@pytest.fixture
def custody(tmp_path, monkeypatch):
    monkeypatch.setattr(secret, 'encrypted_storage', lambda *a, **k: None)
    key = tmp_path / 'admin-vault-key'
    key.write_bytes(secrets.token_bytes(32).hex().encode())
    key.chmod(0o600)
    record = {'machine_id': '1' * 32, 'volume': 'test-volume',
              'luks_uuid': str(uuid.uuid4()), 'recovery_passphrase': secrets.token_hex(32)}
    return tmp_path / 'vault', key, record


def test_authenticated_escrow_is_idempotent_and_ciphertext_only(custody):
    vault, key, record = custody
    exports = []
    def export(data):
        assert data.startswith(b'$ANSIBLE_VAULT;1.2;AES256;luxnix-master\n')
        assert record['recovery_passphrase'].encode() not in data
        exports.append(data)
        return data
    target = provision.escrow_record(vault, key, record, export)
    assert json.loads(secret.decrypt_secret(target, key)) == record
    assert target.stat().st_mode & 0o777 == 0o600
    provision.escrow_record(vault, key, record, export)
    assert exports[0] == exports[1]
    with pytest.raises(provision.ProvisionError, match='conflicts'):
        provision.escrow_record(vault, key, dict(record, recovery_passphrase='different'), export)
    assert len(exports) == 2


def test_failed_export_preserves_primary_for_retry(custody):
    vault, key, record = custody
    def fail(data):
        raise RuntimeError('offline recovery host')
    with pytest.raises(RuntimeError):
        provision.escrow_record(vault, key, record, fail)
    target = provision.escrow_record(vault, key, record, lambda data: data)
    assert json.loads(secret.decrypt_secret(target, key)) == record
    with pytest.raises(provision.ProvisionError, match='export'):
        provision.escrow_record(vault, key, record, lambda data: data[:-1])


def test_controller_only_escrow_can_later_export_same_ciphertext(custody):
    vault, key, record = custody
    path = provision.escrow_record(vault, key, record, None)
    before = path.read_bytes()
    assert json.loads(secret.decrypt_secret(path, key)) == record
    assert record['recovery_passphrase'].encode() not in before
    assert provision.escrow_record(vault, key, record, lambda data: data) == path
    assert path.read_bytes() == before


@pytest.mark.parametrize('extra', [[], ['--controller-only-custody'],
                                  ['--controller-only-custody', '--recovery-host', 'gs-02']])
def test_provision_cannot_defer_independent_recovery(extra):
    with pytest.raises(SystemExit) as exc:
        provision.main(['provision', '--host', 'gc-10', '--volume', 'data', *extra])
    assert exc.value.code == 2


def test_emergency_publisher_repeats_but_never_overwrites(custody, tmp_path):
    vault, key, record = custody
    ciphertext = secret._encrypt_bytes(json.dumps(record).encode(), key, secret.MASTER_VAULT_ID)
    export_home = tmp_path / 'separate-host'
    export_home.mkdir()
    # Execute the production publisher with only its home directory substituted.
    program = provision.EXPORT.replace('Path.home()', 'Path(' + repr(str(export_home)) + ')')
    command = [sys.executable, '-c', program, record['machine_id'], record['luks_uuid']]
    for _ in range(3):
        result = subprocess.run(command, input=ciphertext, capture_output=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ciphertext
    target = export_home / '.luxnix-recovery' / record['machine_id'] / (record['luks_uuid'] + '.vault')
    assert target.stat().st_mode & 0o777 == 0o600
    changed = secret._encrypt_bytes(b'different', key, secret.MASTER_VAULT_ID)
    assert subprocess.run(command, input=changed, capture_output=True).returncode != 0
    assert target.read_bytes() == ciphertext
    assert subprocess.run(command, input=b'plaintext', capture_output=True).returncode != 0


@pytest.fixture
def controller(custody, monkeypatch):
    vault, key, _ = custody
    vault.mkdir(mode=0o700)
    state = SimpleNamespace(layout='legacy-containers', method='passphrase', exists=False, machine_id='1' * 32,
                            luks_uuid=None, requests=[], exports=[], events=[],
                            fail_export=False, connections=[], local_calls=[],
                            recovery_machine_id='2' * 32)
    volume = {'container': '/var/lib/test-volume.luks', 'luksUUID': None}
    config = SimpleNamespace(ansible_root=Path('/test-inventory'),
                             inventory_subnet='test')
    inventory = SimpleNamespace(get_host_by_name=lambda name: (
        SimpleNamespace(ansible_host=name)
        if name in ('test-host', 'recovery-host') else None))
    monkeypatch.setattr(provision, 'AutoconfConfig',
                        SimpleNamespace(load=lambda _: config))
    monkeypatch.setattr(provision, 'AnsibleInventory',
                        SimpleNamespace(load_from_hosts_ini=lambda *args: inventory))
    monkeypatch.setattr(provision, 'encrypted_storage', lambda *args, **kwargs: None)
    monkeypatch.setattr(provision, 'Vault', SimpleNamespace(load_dir=lambda *args:
        SimpleNamespace(validate_local_key=lambda:
                        state.events.append('vault-authenticated'))))
    monkeypatch.setattr(provision.socket, 'gethostname', lambda: 'test-host')

    def target_call(args, data=b'', privileged=False):
        if args[0] == 'sh':
            return b'yes' if state.exists else b'no'
        assert privileged
        if args[:2] == ['cryptsetup', 'luksUUID']:
            return state.luks_uuid.encode()
        if args[:3] == ['cryptsetup', 'open', '--test-passphrase']:
            assert data == state.requests[-1]['recovery_passphrase'].encode()
            return b''
        assert args == ['luxnix-storage-provision', 'test-volume']
        request = json.loads(data)
        primary = Path(request['primary_escrow'])
        assert primary.read_bytes() == state.exports[-1]
        saved = json.loads(secret.decrypt_secret(primary, key))
        assert saved['recovery_passphrase'] == request['recovery_passphrase']
        assert request['emergency_export'].startswith('recovery-host:')
        state.events.append('provision')
        state.requests.append(request)
        state.exists = True
        state.luks_uuid = request['luks_uuid']
        return b''

    def evaluate(args, **kwargs):
        if args[:3] == ['nix', 'eval', '--json']:
            if args[-1].endswith('.layout'):
                return SimpleNamespace(stdout=json.dumps(state.layout).encode())
            if args[3].endswith('.volumes.test-volume'):
                return SimpleNamespace(stdout=json.dumps(volume).encode())
            assert args[3].endswith('.unlockMethod')
            return SimpleNamespace(stdout=json.dumps(state.method).encode())
        state.local_calls.append(args)
        if args == ['cat', '/etc/machine-id']:
            output = state.machine_id.encode()
        elif args == ['sudo', '-n', 'true']:
            output = b''
        elif args[:2] == ['sudo', '-n']:
            output = target_call(args[2:], kwargs['input'], privileged=True)
        else:
            output = target_call(args, kwargs['input'])
        return SimpleNamespace(returncode=0, stdout=output, stderr=b'')
    monkeypatch.setattr(provision.subprocess, 'run', evaluate)

    class Remote:
        def __init__(self, name, password=None):
            self.name = name
            state.connections.append(name)

        def machine_id(self):
            return (state.machine_id if self.name == 'test-host'
                    else state.recovery_machine_id)

        def call(self, args, data=b'', privileged=False):
            if self.name == 'recovery-host':
                assert args[:3] == ['python3', '-c', provision.EXPORT]
                assert data.startswith(b'$ANSIBLE_VAULT;1.2;AES256;luxnix-master\n')
                state.events.append('independent-export')
                if state.fail_export:
                    raise provision.ProvisionError('Recovery host unavailable')
                state.exports.append(data)
                return data
            return target_call(args, data, privileged)

    monkeypatch.setattr(provision, 'Remote', Remote)
    args = ['provision', '--host', 'test-host', '--volume', 'test-volume',
            '--recovery-host', 'recovery-host', '--vault-dir', str(vault),
            '--vault-key', str(key)]
    return args, state, vault, key


@pytest.mark.parametrize('extra', [
    [], ['--backend', 'passphrase'], ['--local-target']])
def test_passphrase_provision_preview_reports_backend_without_custody_or_host_writes(
    controller, capsys, extra
):
    args, state, vault, _ = controller
    provision.main([*args, *extra])
    plan = json.loads(capsys.readouterr().out)
    assert plan['backend'] == 'passphrase'
    assert plan['exists'] is False
    if '--local-target' in extra:
        assert plan['local_target'] is True
        assert state.connections == ['recovery-host']
        assert not any(command[0] == 'sudo' for command in state.local_calls)
    else:
        assert 'local_target' not in plan
        assert state.connections == ['test-host', 'recovery-host']
        assert state.local_calls == []
    assert state.requests == state.exports == state.events == []
    assert not (vault / 'storage-recovery').exists()


@pytest.mark.parametrize('local', [False, True])
def test_passphrase_controller_verifies_both_escrows_then_provisions_same_identity(
    controller, capsys, local
):
    args, state, vault, key = controller
    if local:
        args.append('--local-target')
        state.machine_id = Path('/etc/machine-id').read_text().strip()
    for _ in range(2):
        provision.main([*args, '--apply'])
    assert state.events == [
        'vault-authenticated', 'independent-export', 'provision'] * 2
    assert state.requests[0] == state.requests[1]
    assert state.requests[0]['backend'] == 'passphrase'
    assert state.exports[0] == state.exports[1]
    primary = vault / 'storage-recovery' / state.machine_id / 'test-volume.vault'
    record = json.loads(secret.decrypt_secret(primary, key))
    assert 'backend' not in record
    assert 'local_target' not in record
    assert state.connections == (['recovery-host'] if local else
                                 ['test-host', 'recovery-host']) * 2
    assert record['recovery_passphrase'] not in capsys.readouterr().out


@pytest.mark.parametrize('local', [False, True])
def test_passphrase_controller_never_provisions_without_verified_independent_export(
    controller, local
):
    args, state, vault, key = controller
    if local:
        args.append('--local-target')
        state.machine_id = Path('/etc/machine-id').read_text().strip()
    state.fail_export = True
    with pytest.raises(provision.ProvisionError, match='Recovery host'):
        provision.main([*args, '--apply'])
    primary = vault / 'storage-recovery' / state.machine_id / 'test-volume.vault'
    preserved = primary.read_bytes()
    assert state.requests == []
    state.fail_export = False
    provision.main([*args, '--apply'])
    assert primary.read_bytes() == preserved
    saved = json.loads(secret.decrypt_secret(primary, key))
    assert state.requests[0]['recovery_passphrase'] == saved['recovery_passphrase']


@pytest.mark.parametrize('method', ['tpm2', 'local-openbao'])
def test_controller_rejects_passphrase_policy_override_before_escrow(
    controller, method
):
    args, state, vault, _ = controller
    state.method = method
    with pytest.raises(provision.ProvisionError):
        provision.main([*args, '--backend', 'passphrase', '--apply'])
    assert state.requests == state.exports == state.events == []
    assert not (vault / 'storage-recovery').exists()


@pytest.fixture
def local_process(monkeypatch):
    state = SimpleNamespace(calls=[], sudo_required=False, returncode=0,
                            stdout=b'public output', stderr=b'')
    monkeypatch.setattr(provision.socket, 'gethostname', lambda: 'test-host')
    def run(args, **kwargs):
        state.calls.append((args, kwargs))
        if args == ['sudo', '-n', 'true']:
            return SimpleNamespace(returncode=int(state.sudo_required),
                                   stdout=b'', stderr=b'')
        return SimpleNamespace(returncode=state.returncode,
                               stdout=state.stdout, stderr=state.stderr)
    monkeypatch.setattr(provision.subprocess, 'run', run)
    return state


def test_local_argv_stdin_and_remote_ssh_quoting_remain_distinct(local_process):
    args = ['printf', '%s', 'literal space', '$(must-not-run)']
    data = b'synthetic stdin payload'
    assert provision.Local('test-host').call(args, data) == b'public output'
    local_args, options = local_process.calls[-1]
    assert local_args == args
    assert options['input'] == data
    assert options['capture_output'] is True
    assert options['timeout'] == 600
    provision.Remote('172.16.255.102').call(args, data)
    remote_args, options = local_process.calls[-1]
    assert remote_args[0] == 'ssh'
    assert remote_args[-2] == 'admin@172.16.255.102'
    assert remote_args[-1] == "printf %s 'literal space' '$(must-not-run)'"
    assert options['input'] == data


@pytest.mark.parametrize('password_required', [False, True])
def test_local_privileged_calls_use_existing_sudo_and_private_stdin_policy(
    local_process, tmp_path, monkeypatch, password_required
):
    local_process.sudo_required = password_required
    password = tmp_path / 'sudo-password'
    password.write_bytes(b'synthetic-sudo-password\n')
    password.chmod(0o600)
    checked = []
    monkeypatch.setattr(provision, 'encrypted_storage',
                        lambda path, **kwargs: checked.append(path))
    target = provision.Local('test-host', password)
    for _ in range(2):
        target.call(['luxnix-storage-provision', 'test-volume'],
                    b'synthetic request', privileged=True)
    assert local_process.calls[0][0] == ['sudo', '-n', 'true']
    assert local_process.calls[0][1]['timeout'] == 30
    assert len(local_process.calls) == 3
    prefix = ['sudo', '-k', '-S', '-p', ''] if password_required else ['sudo', '-n']
    for args, options in local_process.calls[1:]:
        assert args == [*prefix, 'luxnix-storage-provision', 'test-volume']
        assert 'synthetic-sudo-password' not in ' '.join(args)
        expected = b'synthetic request'
        if password_required:
            expected = b'synthetic-sudo-password\n' + expected
        assert options['input'] == expected
    assert checked == ([password, password] if password_required else [])


def test_local_failure_redacts_subprocess_input_and_diagnostics(local_process):
    local_process.returncode = 1
    local_process.stderr = b'failure involving synthetic-secret-content'
    with pytest.raises(provision.ProvisionError) as exc:
        provision.Local('test-host').call(['test-command'],
                                           b'synthetic-secret-content')
    assert 'synthetic-secret-content' not in str(exc.value)
    assert 'exit 1' in str(exc.value)


def test_local_target_requires_exact_os_hostname_before_execution(local_process):
    with pytest.raises(provision.ProvisionError):
        provision.Local('test-host.example')
    assert local_process.calls == []


def test_local_machine_identity_requires_valid_machine_id(local_process):
    local_process.stdout = b'invalid-machine-id\n'
    with pytest.raises(provision.ProvisionError, match='machine identity'):
        provision.Local('test-host').machine_id()
    assert [args for args, _ in local_process.calls] == [['cat', '/etc/machine-id']]


@pytest.mark.parametrize(('local', 'same_as'), [
    (False, 'target'), (False, 'controller'), (True, 'target')])
def test_recovery_host_must_differ_from_target_and_controller(
    controller, local, same_as
):
    args, state, vault, _ = controller
    controller_id = Path('/etc/machine-id').read_text().strip()
    if local:
        args.append('--local-target')
        state.machine_id = controller_id
    state.recovery_machine_id = (state.machine_id if same_as == 'target'
                                 else controller_id)
    with pytest.raises(provision.ProvisionError, match='separate host'):
        provision.main([*args, '--apply'])
    assert state.requests == state.exports == state.events == []
    assert not (vault / 'storage-recovery').exists()


def test_boot_luks_rejects_container_creation_before_connections(controller):
    args, state, vault, _ = controller
    state.layout = 'boot-luks'
    with pytest.raises(provision.ProvisionError, match='retired'):
        provision.main([*args, '--apply'])
    assert state.connections == []
    assert state.requests == []
