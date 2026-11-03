"""Recovery custody uses real Ansible encryption and disposable synthetic data."""
import json
import os
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


@pytest.mark.parametrize('optimization', [[], ['-O']])
def test_emergency_publisher_repeats_but_never_overwrites(custody, tmp_path, optimization):
    vault, key, record = custody
    ciphertext = secret._encrypt_bytes(json.dumps(record).encode(), key, secret.MASTER_VAULT_ID)
    export_home = tmp_path / 'separate-host'
    export_home.mkdir()
    # Execute the production publisher with only its home directory substituted.
    program = provision.EXPORT.replace('Path.home()', 'Path(' + repr(str(export_home)) + ')')
    command = [sys.executable, *optimization, '-c', program, record['machine_id'], record['luks_uuid']]
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


@pytest.mark.parametrize('optimization', [[], ['-O']])
@pytest.mark.parametrize('kind', ['volume', 'openbao-local'])
@pytest.mark.parametrize('fault', ['identity', 'ciphertext', 'directory-symlink',
                                  'directory-mode', 'lock-symlink', 'lock-fifo',
                                  'target-symlink', 'target-fifo', 'target-mode',
                                  'target-hardlink'])
def test_shared_recovery_publisher_rejects_unsafe_exports(
    custody, tmp_path, optimization, kind, fault
):
    from lx_administration.storage.recovery_export import export_script
    _, key, record = custody
    ciphertext = secret._encrypt_bytes(b'{}', key, secret.MASTER_VAULT_ID)
    home = tmp_path / 'recovery-host'
    home.mkdir()
    root = home / '.luxnix-recovery'
    root.mkdir(mode=0o700)
    owner, identifier = ((record['machine_id'], record['luks_uuid']) if kind == 'volume'
                         else ('gc-10', 'seal-key'))
    parent = root / owner if kind == 'volume' else root / kind / owner
    parent.mkdir(mode=0o700, parents=True)
    # parents=True uses default permissions for intermediate directories.
    if kind == 'openbao-local':
        parent.parent.chmod(0o700)
    target = parent / (identifier + '.vault')
    outside = tmp_path / 'untouched'
    outside.write_bytes(b'preserved')
    outside.chmod(0o600)
    if fault == 'identity':
        owner = '../escape'
    elif fault == 'ciphertext':
        ciphertext = b'$ANSIBLE_VAULT;1.2;AES256;luxnix-master\nplaintext\n'
    elif fault == 'directory-symlink':
        parent.rmdir()
        parent.symlink_to(tmp_path, target_is_directory=True)
    elif fault == 'directory-mode':
        parent.chmod(0o755)
    elif fault == 'lock-symlink':
        (root / '.lock').symlink_to(outside)
    elif fault == 'lock-fifo':
        os.mkfifo(root / '.lock', mode=0o600)
    elif fault == 'target-symlink':
        target.symlink_to(outside)
    elif fault == 'target-fifo':
        os.mkfifo(target, mode=0o600)
    elif fault == 'target-mode':
        target.write_bytes(ciphertext)
        target.chmod(0o644)
    elif fault == 'target-hardlink':
        os.link(outside, target)
    program = export_script(kind).replace('Path.home()', 'Path(' + repr(str(home)) + ')')
    result = subprocess.run([sys.executable, *optimization, '-c', program, owner, identifier],
                            input=ciphertext, capture_output=True, timeout=5)
    assert result.returncode != 0
    assert result.stdout == b''
    assert outside.read_bytes() == b'preserved'
    assert not list(parent.glob('.recovery-*'))


@pytest.fixture(params=["legacy-containers"])
def controller(custody, monkeypatch, request):
    vault, key, _ = custody
    vault.mkdir(mode=0o700)
    # Independent native-age custody has its own real-crypto test lane; these
    # controller tests isolate the existing vault/export/target sequence.
    monkeypatch.setattr(provision, 'require_independent_custody', lambda *_: None)
    state = SimpleNamespace(layout=request.param, method='passphrase', exists=False, machine_id='1' * 32,
                            luks_uuid=None, requests=[], exports=[], events=[],
                            fail_export=False, connections=[], local_calls=[],
                            recovery_machine_id='2' * 32)
    volume = {'container': '/var/lib/test-volume.luks', 'luksUUID': None}
    config = SimpleNamespace(ansible_root=Path('/test-inventory'),
                             inventory_subnet='test')
    inventory = SimpleNamespace(get_host_by_name=lambda name: (
        SimpleNamespace(ansible_host=name)
        if name in ('gc-10', 'recovery-host') else None))
    monkeypatch.setattr(provision, 'AutoconfConfig',
                        SimpleNamespace(load=lambda _: config))
    monkeypatch.setattr(provision, 'AnsibleInventory',
                        SimpleNamespace(load_from_hosts_ini=lambda *args: inventory))
    monkeypatch.setattr(provision, 'encrypted_storage', lambda *args, **kwargs: None)
    monkeypatch.setattr(provision, 'Vault', SimpleNamespace(load_dir=lambda *args:
        SimpleNamespace(validate_local_key=lambda:
                        state.events.append('vault-authenticated'))))
    monkeypatch.setattr(provision.socket, 'gethostname', lambda: 'gc-10')

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

    # Controller tests model an already authenticated payload stream. The real
    # privilege handshake and password isolation run in test_storage_sudo_transport.
    def local_stream(self, args, privileged=True, timeout=30):
        assert privileged
        state.local_calls.append(['authenticated-stream', *args])
        class Stream:
            returncode = 0
            def communicate(self, data, timeout):
                return target_call(args, data, privileged=True), b''
        return Stream()
    monkeypatch.setattr(provision.Local, 'open_stream', local_stream)

    class Remote:
        def __init__(self, name, password=None):
            self.name = name
            state.connections.append(name)

        def machine_id(self):
            return (state.machine_id if self.name == 'gc-10'
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
    args = ['provision', '--host', 'gc-10', '--volume', 'test-volume',
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
        assert state.connections == ['gc-10', 'recovery-host']
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
                                 ['gc-10', 'recovery-host']) * 2
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
    monkeypatch.setattr(provision.socket, 'gethostname', lambda: 'gc-10')
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
    assert provision.Local('gc-10').call(args, data) == b'public output'
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


def test_local_privileged_calls_send_only_payload_after_authenticated_stream(local_process, monkeypatch):
    sent = []
    class Stream:
        returncode = 0
        def communicate(self, data, timeout):
            sent.append(data)
            return b'public output', b''
    target = provision.Local('gc-10')
    calls = []
    def ready(args):
        calls.append(args)
        return Stream()
    monkeypatch.setattr(target, 'open_stream', ready)
    for _ in range(2):
        assert target.call(['luxnix-storage-provision', 'test-volume'],
                           b'synthetic request', privileged=True) == b'public output'
    assert calls == [['luxnix-storage-provision', 'test-volume']] * 2
    assert sent == [b'synthetic request'] * 2
    assert not local_process.calls


def test_local_failure_redacts_subprocess_input_and_diagnostics(local_process):
    local_process.returncode = 1
    local_process.stderr = b'failure involving synthetic-secret-content'
    with pytest.raises(provision.ProvisionError) as exc:
        provision.Local('gc-10').call(['test-command'],
                                           b'synthetic-secret-content')
    assert 'synthetic-secret-content' not in str(exc.value)
    assert 'exit 1' in str(exc.value)


def test_local_target_requires_exact_os_hostname_before_execution(local_process):
    with pytest.raises(provision.ProvisionError):
        provision.Local('gc-10.example')
    assert local_process.calls == []


def test_local_machine_identity_requires_valid_machine_id(local_process):
    local_process.stdout = b'invalid-machine-id\n'
    with pytest.raises(provision.ProvisionError, match='machine identity'):
        provision.Local('gc-10').machine_id()
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


@pytest.mark.parametrize("host,layout,backend", [
    ("gc-02", "legacy-containers", None),
    ("gc-10", "unencrypted-root", None),
    ("gc-10", "legacy-containers", "tpm2"),
    ("gc-10", "legacy-containers", "local-openbao"),
])
def test_retired_container_enrollment_fails_before_connections(
    controller, host, layout, backend
):
    args, state, _, _ = controller
    args[args.index("--host") + 1] = host
    state.layout = layout
    if backend:
        args += ["--backend", backend]
    with pytest.raises(provision.ProvisionError, match="retired"):
        provision.main(args + ["--apply"])
    assert state.connections == state.requests == state.events == []
