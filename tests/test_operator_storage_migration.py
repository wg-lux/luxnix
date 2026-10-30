"""Exercise real rsync copies on disposable files; never open or format a device."""
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from lx_administration.storage import operator_migration as migration


@pytest.fixture
def layout(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    volume = tmp_path / "encrypted"
    volume.mkdir()
    config = {"volumes": {"data": {"mountPoint": str(volume)}},
              "binds": {str(source): {"volume": "data", "directory": "data"}}, "writers": ["consumer"]}
    original = migration.run
    def run(*args, **kwargs):
        if args[0] == "systemctl":
            return b"0\n"
        if args[0] == "findmnt":
            return b"test-filesystem-uuid\n"
        return original(*args, **kwargs)
    monkeypatch.setattr(migration, "run", run)
    monkeypatch.setattr(migration.os.path, "ismount", lambda path: path == volume)
    verifier = SimpleNamespace(encrypted_storage=lambda path: None)
    return source, volume, migration.Migration(config, verifier)


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync required")
def test_copy_verifies_metadata_hardlinks_and_does_not_recopy_stale_source(layout):
    source, volume, task = layout
    (source / "record").write_bytes(b"original data")
    (source / "record").chmod(0o600)
    os.link(source / "record", source / "linked")
    task.prepare()
    destination = volume / "data"
    assert (destination / "record").read_bytes() == b"original data"
    assert (destination / "record").stat().st_mode & 0o777 == 0o600
    assert (destination / "record").stat().st_ino == (destination / "linked").stat().st_ino
    assert (source / "record").exists()
    (destination / "record").write_bytes(b"new application data")
    task.prepare()
    assert (destination / "record").read_bytes() == b"new application data"


def test_unencrypted_target_is_rejected_before_copy(layout):
    source, volume, task = layout
    def reject(path):
        raise ValueError("unencrypted")
    task.verifier.encrypted_storage = reject
    with pytest.raises(ValueError):
        task.prepare()
    assert list(volume.iterdir()) == []


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync required")
def test_conflicting_populated_destination_is_never_overwritten(layout):
    source, volume, task = layout
    (source / "record").write_text("source")
    (volume / "data").mkdir()
    (volume / "data" / "record").write_text("existing encrypted data")
    with pytest.raises(migration.MigrationError, match="refusing overwrite"):
        task.prepare()
    assert (volume / "data" / "record").read_text() == "existing encrypted data"


def test_running_writer_is_not_stopped_or_copied(layout, monkeypatch):
    source, volume, task = layout
    original = migration.run
    monkeypatch.setattr(migration, "run", lambda *args, **kwargs: b"123\n" if args[0] == "systemctl" else original(*args, **kwargs))
    with pytest.raises(migration.MigrationError, match="writer is running"):
        task.prepare()
    assert not (volume / "data").exists()


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync required")
def test_interrupted_private_copy_resumes_and_verifies(layout, monkeypatch):
    source, volume, task = layout
    (source / "record").write_text("preserved source")
    original = migration.staged_copy.rsync
    monkeypatch.setattr(migration.staged_copy, "rsync", lambda *args, **kwargs: (_ for _ in ()).throw(migration.staged_copy.CutoverError("interrupted")))
    with pytest.raises(migration.MigrationError):
        task.prepare()
    assert (volume / "data.luxnix-copy" / "plan.json").exists()
    monkeypatch.setattr(migration.staged_copy, "rsync", original)
    task.prepare()
    assert (volume / "data" / "record").read_text() == "preserved source"
    assert not (volume / "data.luxnix-copy").exists()


def test_existing_container_is_never_formatted(tmp_path, monkeypatch):
    container = tmp_path / "already-populated.luks"
    container.write_bytes(b"existing content must not be overwritten")
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        if args[:2] == ("cryptsetup", "isLuks"):
            raise migration.MigrationError("not LUKS")
        raise AssertionError(args)
    monkeypatch.setattr(migration, "run", run)
    task = migration.Migration({"volumes": {"data": {"container": str(container), "device": "/dev/mapper/test-never-created"}}},
                               SimpleNamespace(_require_protected_swap=lambda: None))
    with pytest.raises(migration.MigrationError):
        task.unlock("data")
    assert calls == [("cryptsetup", "isLuks", str(container))]
    assert container.read_bytes() == b"existing content must not be overwritten"


def test_account_hash_copy_preserves_bytes_and_follows_source(tmp_path):
    source, target = tmp_path / "source", tmp_path / "boot" / "account.hash"
    source.write_bytes(b"existing account hash\n")
    source.chmod(0o600)
    migration.prepare_accounts({str(target): str(source)})
    assert target.read_bytes() == source.read_bytes()
    assert target.stat().st_mode & 0o777 == 0o600
    source.write_bytes(b"rotated account hash\n")
    migration.prepare_accounts({str(target): str(source)})
    assert target.read_bytes() == b"rotated account hash\n"
    assert target.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in target.parent.iterdir()) == ["account.hash"]


def test_account_hash_copy_keeps_target_while_source_is_locked_or_unsafe(tmp_path):
    source, target = tmp_path / "source", tmp_path / "boot" / "account.hash"
    target.parent.mkdir()
    target.write_bytes(b"current account hash\n")
    migration.prepare_accounts({str(target): str(source)})
    assert target.read_bytes() == b"current account hash\n"
    source.write_bytes(b"group readable hash\n")
    source.chmod(0o640)
    migration.prepare_accounts({str(target): str(source)})
    assert target.read_bytes() == b"current account hash\n"


def test_account_hash_copy_never_replaces_target_with_retired_hash(tmp_path, monkeypatch):
    # A disposable stand-in; the real retired credential is not kept in tests.
    retired = b"$6$standin$retired-credential"
    monkeypatch.setattr(
        migration, "RETIRED_ACCOUNT_HASH_DIGESTS", frozenset({hashlib.sha256(retired).hexdigest()})
    )
    source, target = tmp_path / "source", tmp_path / "boot" / "account.hash"
    target.parent.mkdir()
    target.write_bytes(b"unique account hash\n")
    source.write_bytes(retired + b"\n")
    source.chmod(0o600)
    migration.prepare_accounts({str(target): str(source)})
    assert target.read_bytes() == b"unique account hash\n"


def test_missing_account_hash_copy_still_requires_private_source(tmp_path):
    source, target = tmp_path / "source", tmp_path / "boot" / "account.hash"
    source.write_bytes(b"group readable hash\n")
    source.chmod(0o640)
    with pytest.raises(migration.MigrationError):
        migration.prepare_accounts({str(target): str(source)})
    assert not target.exists()


@pytest.mark.parametrize("method", ["passphrase", "tpm2"])
def test_missing_container_never_provisions_during_startup(tmp_path, monkeypatch, method):
    container = tmp_path / "missing.luks"
    monkeypatch.setattr(migration, "require_secure_boot", lambda: None)
    monkeypatch.setattr(migration, "run", lambda *a, **k: pytest.fail("Startup must not create storage"))
    task = migration.Migration({"unlockMethod": method,
        "volumes": {"data": {"container": str(container), "device": "/dev/mapper/test-never-created"}}},
        SimpleNamespace(_require_protected_swap=lambda: None))
    with pytest.raises(migration.MigrationError):
        task.unlock("data")
    assert not container.exists()


def test_explicit_provision_uses_escrowed_key_and_never_reformats(tmp_path, monkeypatch):
    container = tmp_path / "new.luks"
    record = {"machine_id": Path('/etc/machine-id').read_text().strip(), "volume": "data",
        "luks_uuid": "5d36ce47-893c-4fbc-9527-1cc6b420d2be", "recovery_passphrase": "a" * 64,
        "primary_escrow": "test-vault-reference", "emergency_export": "test-independent-reference"}
    calls = []
    def run(*args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == 'systemd-cryptenroll':
            fd = kwargs['pass_fds'][0]
            assert os.read(fd, 1000) == record['recovery_passphrase'].encode()
        if args[:2] == ('cryptsetup', 'luksUUID'):
            return record['luks_uuid'].encode()
        return b''
    monkeypatch.setattr(migration, 'run', run)
    monkeypatch.setattr(migration, 'require_secure_boot', lambda: None)
    monkeypatch.setattr(migration.os, 'posix_fallocate', lambda fd, offset, size: os.ftruncate(fd, size))
    task = migration.Migration({'unlockMethod': 'tpm2', 'binds': {}, 'volumes': {'data': {
        'container': str(container), 'device': '/dev/mapper/test-never-created', 'minimumSizeMiB': 1}}},
        SimpleNamespace(_require_protected_swap=lambda: None))
    monkeypatch.setattr(task, 'unlock', lambda name: None)
    task.provision('data', record)
    assert container.stat().st_mode & 0o777 == 0o600
    assert sum(args[:2] == ('cryptsetup', 'luksFormat') for args, _ in calls) == 1
    for args, _ in calls:
        assert record['recovery_passphrase'] not in ' '.join(args)
    task.provision('data', record)
    assert sum(args[:2] == ('cryptsetup', 'luksFormat') for args, _ in calls) == 1
    container.with_suffix('.luks.provisioned.json').unlink()
    with pytest.raises(migration.MigrationError, match='never reformat'):
        task.provision('data', record)
    assert container.exists()


@pytest.fixture
def tpm_layout(tmp_path, monkeypatch):
    container = tmp_path / "enrolled.luks"
    container.write_bytes(b"preserved encrypted volume")
    task = migration.Migration({"unlockMethod": "tpm2", "tpm2PluginPath": "/systemd/lib/cryptsetup",
        "volumes": {"data": {"container": str(container), "device": "/dev/mapper/test-never-created"}}},
        SimpleNamespace(_require_protected_swap=lambda: None))
    monkeypatch.setattr(migration, "require_secure_boot", lambda: None)
    return container, task


def test_tpm_unlock_is_headless_and_preserves_container(tpm_layout, monkeypatch):
    container, task = tpm_layout
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        if args[1] == "luksDump":
            return json.dumps({"tokens": {"0": {"type": "systemd-tpm2", "tpm2-pcrs": [7]}}}).encode()
        return b""
    monkeypatch.setattr(migration, "run", run)
    task.unlock("data")
    assert calls[-1] == ("cryptsetup", "open", "--type", "luks", "--token-only", "--token-type", "systemd-tpm2",
                         "--token-id", "0", "--external-tokens-path", "/systemd/lib/cryptsetup",
                         str(container), "test-never-created")
    assert container.read_bytes() == b"preserved encrypted volume"
    assert len(calls) == 2


@pytest.mark.parametrize("tokens", [{}, {"0": {"type": "systemd-tpm2", "tpm2-pcrs": []}},
    {"0": {"type": "systemd-tpm2", "tpm2-pcrs": [7], "tpm2-pin": True}},
    {"0": {"type": "systemd-tpm2", "tpm2-pcrs": [7]},
     "1": {"type": "systemd-tpm2", "tpm2-pcrs": []}}])
def test_tpm_rejects_missing_weak_or_interactive_enrollment(tpm_layout, monkeypatch, tokens):
    _, task = tpm_layout
    def run(*args, **kwargs):
        assert args[:3] == ("cryptsetup", "luksDump", "--dump-json-metadata")
        return json.dumps({"tokens": tokens}).encode()
    monkeypatch.setattr(migration, "run", run)
    with pytest.raises(migration.MigrationError, match="enrollment"):
        task.unlock("data")


def test_tpm_never_creates_missing_container(tpm_layout, monkeypatch):
    container, task = tpm_layout
    container.unlink()
    monkeypatch.setattr(migration, "run", lambda *a, **k: pytest.fail("Unexpected subprocess"))
    with pytest.raises(migration.MigrationError, match="provisioned"):
        task.unlock("data")
    assert not container.exists()


def test_tpm_failure_does_not_fall_back_to_prompt(tpm_layout, monkeypatch):
    _, task = tpm_layout
    def run(*args, **kwargs):
        if args[1] == "luksDump":
            return json.dumps({"tokens": {"0": {"type": "systemd-tpm2", "tpm2-pcrs": [7]}}}).encode()
        assert args[:2] == ("cryptsetup", "open")
        raise migration.MigrationError("TPM unavailable")
    monkeypatch.setattr(migration, "run", run)
    with pytest.raises(migration.MigrationError, match="TPM unavailable"):
        task.unlock("data")


@pytest.mark.parametrize("value", [None, b"", b"\x07\x00\x00\x00\x00", b"\x07\x00\x00\x00\x01"])
def test_secure_boot_requires_enabled_firmware_variable(monkeypatch, value):
    monkeypatch.setattr(Path, "is_file", lambda self: value is not None)
    monkeypatch.setattr(Path, "read_bytes", lambda self: value)
    if value is not None and value[4:] == b"\x01":
        migration.require_secure_boot()
    else:
        with pytest.raises(migration.MigrationError, match="Secure Boot"):
            migration.require_secure_boot()


def test_wrong_native_uuid_is_rejected_before_unlock(tpm_layout, monkeypatch):
    _, task = tpm_layout
    task.config['volumes']['data']['luksUUID'] = 'expected-native-uuid'
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return b'foreign-native-uuid'
    monkeypatch.setattr(migration, 'run', run)
    with pytest.raises(migration.MigrationError, match='UUID'):
        task.unlock('data')
    assert len(calls) == 1 and calls[0][:2] == ('cryptsetup', 'luksUUID')


def test_local_openbao_unlock_uses_uuid_and_stdin_only(tmp_path, monkeypatch):
    import runpy
    container = tmp_path / "data.luks"
    container.write_bytes(b"preserved")
    token_dir = tmp_path / "credentials"
    config = {
        "unlockMethod": "local-openbao", "machine": "host", "openbaoClient": "client.py",
        "volumes": {"data": {"container": str(container), "device": "/dev/mapper/test-local",
                             "luksUUID": "expected-uuid"}},
    }
    calls = []
    keys = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return b"expected-uuid\n" if args[1] == "luksUUID" else b""

    def fetch(*args):
        keys.append(args)
        return b"x" * 32

    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(token_dir))
    monkeypatch.setattr(migration, "run", run)
    monkeypatch.setattr(runpy, "run_path", lambda _: {"volume_key": fetch})
    task = migration.Migration(config, SimpleNamespace(_require_protected_swap=lambda: None))
    task.unlock("data")
    assert keys == [("host", "data", "expected-uuid", token_dir / "volume.unlock")]
    assert calls[-1][0] == ("cryptsetup", "open", "--type", "luks", "--key-file=-", str(container), "test-local")
    assert calls[-1][1] == {"input": b"x" * 32}
    assert container.read_bytes() == b"preserved"
    calls.clear()
    config["volumes"]["data"]["luksUUID"] = "wrong"
    with pytest.raises(migration.MigrationError, match="UUID"):
        task.unlock("data")
    assert len(calls) == 1


@pytest.fixture
def local_provision(tmp_path, monkeypatch):
    container = tmp_path / 'new.luks'
    device = tmp_path / 'mapper'
    expected_uuid = '11111111-1111-1111-1111-111111111111'
    task = migration.Migration({'unlockMethod': 'local-openbao', 'machine': 'test-host', 'binds': {},
        'volumes': {'data': {'container': str(container), 'device': str(device),
                            'luksUUID': expected_uuid, 'minimumSizeMiB': 1}}},
        SimpleNamespace(_require_protected_swap=lambda: None))
    record = {'machine_id': '1' * 32, 'volume': 'data', 'luks_uuid': expected_uuid,
              'host': 'test-host', 'container': str(container), 'origin': 'new',
              'recovery_passphrase': 'a' * 64, 'provisioner': {'role_id': 'test-role'},
              'primary_escrow': 'verified-test', 'emergency_export': 'verified-test-independent'}
    state = SimpleNamespace(fs=False, filesystem='ext4', formatted=False,
                            calls=[], inputs=[], fail=None)
    def command(*args, **kwargs):
        state.calls.append(args)
        state.inputs.append(kwargs.get('input'))
        if args[:2] == ('cryptsetup', 'luksUUID'):
            return expected_uuid.encode()
        if args[:2] == ('cryptsetup', 'luksFormat'):
            if state.fail == 'format':
                raise migration.MigrationError('interrupted allocation format')
            state.formatted = True
        if args[0] == 'mkfs.ext4':
            if state.fail == 'mkfs':
                raise migration.MigrationError('interrupted filesystem creation')
            state.fs = True
        return b''
    monkeypatch.setattr(migration, 'run', command)
    monkeypatch.setattr(migration.os, 'posix_fallocate', lambda fd, offset, size: os.ftruncate(fd, size))
    def probe(args, **kwargs):
        if args[:2] == ['cryptsetup', 'isLuks']:
            return SimpleNamespace(returncode=0 if state.formatted else 1, stdout=b'')
        return SimpleNamespace(returncode=0 if state.fs else 2,
                               stdout=state.filesystem.encode() if state.fs else b'')
    monkeypatch.setattr(migration.subprocess, 'run', probe)
    host = SimpleNamespace(
        volume_record=lambda *a: state.calls.append(('record',)) or b'x' * 32,
        convert_volume=lambda *a: state.calls.append(('keyslot',)))
    return task, record, host, state, container


def test_local_provision_resumes_without_tpm_token_or_reformat(local_provision):
    task, record, host, state, container = local_provision
    state.fail = 'mkfs'
    with pytest.raises(migration.MigrationError, match='interrupted'):
        task.provision_container('data', record, record['recovery_passphrase'].encode(),
                                 record['luks_uuid'], openbao=host)
    assert container.exists()
    assert not container.with_suffix('.luks.provisioned.json').exists()
    state.fail = None
    for _ in range(2):
        task.provision_container('data', record, record['recovery_passphrase'].encode(),
                                 record['luks_uuid'], openbao=host)
    assert sum(c[:2] == ('cryptsetup', 'luksFormat') for c in state.calls) == 1
    assert state.calls.index(('record',)) < next(i for i,c in enumerate(state.calls) if c[:2] == ('cryptsetup', 'luksFormat'))
    assert not any(c[0] == 'systemd-cryptenroll' for c in state.calls)
    assert not any(record['recovery_passphrase'] in ' '.join(c) for c in state.calls)
    assert container.with_suffix('.luks.provisioned.json').exists()
    assert not container.with_suffix('.luks.provisioning.json').exists()


def test_local_provision_refuses_foreign_uuid_and_existing_volume_escrow(local_provision, monkeypatch):
    task, record, host, state, container = local_provision
    record['origin'] = 'existing'
    with pytest.raises(migration.MigrationError, match='adopt existing'):
        task.provision_container('data', record, b'a' * 64,
                                 record['luks_uuid'], openbao=host)
    assert not container.exists()
    record['origin'] = 'new'
    container.write_bytes(b'foreign encrypted data')
    identity = {key: record[key] for key in ('machine_id', 'volume', 'luks_uuid')}
    migration.atomic_json(container.with_suffix('.luks.provisioning.json'), identity)
    monkeypatch.setattr(migration, 'run', lambda *a, **k: b'foreign-uuid')
    with pytest.raises(migration.MigrationError, match='never reformat'):
        task.provision_container('data', record, b'a' * 64,
                                 record['luks_uuid'], openbao=host)
    assert container.read_bytes() == b'foreign encrypted data'


def test_precopy_keeps_live_writers_and_final_prepare_captures_delta(layout, monkeypatch):
    source, volume, task = layout
    (source / 'record').write_text('live-1')
    original = migration.run
    monkeypatch.setattr(migration, 'run', lambda *a, **k:
        pytest.fail('Pre-copy must not inspect or stop writers') if a[0] == 'systemctl' else original(*a, **k))
    task.precopy()
    assert not (volume / 'data').exists()
    (source / 'record').write_text('final-2')
    monkeypatch.setattr(migration, 'run', original)
    task.prepare()
    assert (volume / 'data/record').read_text() == 'final-2'
    assert (source / 'record').read_text() == 'final-2'


def test_failed_multi_directory_cutover_rolls_publications_back_to_staging(layout, monkeypatch):
    source, volume, task = layout
    (source / 'record').write_text('before')
    second = source.parent / 'second'
    second.mkdir()
    (second / 'record').write_text('second')
    task.config['binds'][str(second)] = {'volume': 'data', 'directory': 'second'}
    pending = [(*item, item[1].exists()) for item in task.pending_copies()]
    original = migration.staged_copy.cutover
    def fail_second(item, *args):
        if item.source == second:
            raise migration.staged_copy.CutoverError('injected final copy failure')
        return original(item, *args)
    monkeypatch.setattr(migration.staged_copy, 'cutover', fail_second)
    with pytest.raises(migration.MigrationError, match='injected'):
        task.prepare()
    task.rollback_copies(pending)
    assert not (volume / 'data').exists()
    assert not list((volume / '.luxnix-migrations').glob('*.json'))
    # Writers can change the originals after recovery; retry must not use stale receipts.
    (source / 'record').write_text('after recovery')
    monkeypatch.setattr(migration.staged_copy, 'cutover', original)
    task.prepare()
    assert (volume / 'data/record').read_text() == 'after recovery'


def test_local_provision_recovers_an_unpublished_allocation(local_provision):
    task, record, host, state, container = local_provision
    state.fail = 'format'
    with pytest.raises(migration.MigrationError, match='allocation'):
        task.provision_container('data', record, b'a' * 64,
                                 record['luks_uuid'], openbao=host)
    assert not container.exists()
    assert Path(str(container) + '.allocating').exists()
    state.fail = None
    task.provision_container('data', record, b'a' * 64,
                             record['luks_uuid'], openbao=host)
    assert container.exists()
    assert not Path(str(container) + '.allocating').exists()
    assert all(c[-1].endswith('.allocating') for c in state.calls if c[:2] == ('cryptsetup', 'luksFormat'))


@pytest.mark.parametrize("reason", ["tpm-not-physical", "secure-boot-disabled"])
def test_public_local_provision_checks_platform_before_allocation(
    local_provision, monkeypatch, reason
):
    import runpy
    from lx_administration.storage import openbao_enroll

    task, record, _, state, container = local_provision
    task.config.update(localOpenbaoEnabled=True, openbaoEnroll="enroll.py",
                       openbaoClient="client.py")
    record["machine_id"] = Path("/etc/machine-id").read_text().strip()
    monkeypatch.setattr(migration, "require_secure_boot", lambda: None)
    def refuse():
        raise ValueError(reason)
    def load(path):
        return (vars(openbao_enroll) if path == "enroll.py"
                else {"platform_preflight": refuse})
    monkeypatch.setattr(runpy, "run_path", load)
    with pytest.raises(migration.MigrationError, match=reason):
        task.provision("data", record)
    assert state.calls == []
    assert not container.exists()


@pytest.fixture
def passphrase_provision(local_provision, monkeypatch):
    task, record, _, state, container = local_provision
    task.config['unlockMethod'] = 'passphrase'
    task.config['volumes']['data']['luksUUID'] = None
    record.update(backend='passphrase',
                  machine_id=Path('/etc/machine-id').read_text().strip())
    record.pop('provisioner')
    monkeypatch.setattr(
        migration, 'require_secure_boot',
        lambda: pytest.fail('Passphrase provisioning must not require Secure Boot'))
    monkeypatch.setattr(
        migration.runpy, 'run_path',
        lambda _: pytest.fail('Passphrase provisioning must not contact OpenBao'))
    return task, record, state, container


def test_public_passphrase_provision_creates_once_using_only_escrowed_key(
    passphrase_provision
):
    task, record, state, container = passphrase_provision
    for _ in range(2):
        task.provision('data', record)
    assert container.stat().st_mode & 0o777 == 0o600
    assert sum(c[:2] == ('cryptsetup', 'luksFormat') for c in state.calls) == 1
    assert sum(c[0] == 'mkfs.ext4' for c in state.calls) == 1
    assert not any(c[0] in ('systemd-cryptenroll', 'record', 'keyslot')
                   for c in state.calls)
    for command, data in zip(state.calls, state.inputs):
        assert record['recovery_passphrase'] not in ' '.join(command)
        if '--key-file=-' in command:
            assert data == record['recovery_passphrase'].encode()
    receipt = json.loads(container.with_suffix('.luks.provisioned.json').read_text())
    assert receipt == {
        key: record[key] for key in ('machine_id', 'volume', 'luks_uuid')}
    assert not container.with_suffix('.luks.provisioning.json').exists()


@pytest.mark.parametrize('failure', ['format', 'mkfs'])
def test_public_passphrase_provision_resumes_without_reformatting_published_container(
    passphrase_provision, failure
):
    task, record, state, container = passphrase_provision
    state.fail = failure
    with pytest.raises(migration.MigrationError, match='interrupted'):
        task.provision('data', record)
    assert container.exists() == (failure == 'mkfs')
    assert container.with_suffix('.luks.provisioning.json').exists()
    assert not container.with_suffix('.luks.provisioned.json').exists()
    state.fail = None
    task.provision('data', record)
    assert container.with_suffix('.luks.provisioned.json').exists()
    assert not Path(str(container) + '.allocating').exists()
    assert all(c[-1].endswith('.allocating') for c in state.calls
               if c[:2] == ('cryptsetup', 'luksFormat'))
    formats = sum(c[:2] == ('cryptsetup', 'luksFormat') for c in state.calls)
    assert formats == (2 if failure == 'format' else 1)


@pytest.mark.parametrize('method', ['tpm2', 'local-openbao'])
def test_passphrase_backend_cannot_bypass_configured_unlock_policy(
    passphrase_provision, method
):
    task, record, state, container = passphrase_provision
    task.config['unlockMethod'] = method
    with pytest.raises(migration.MigrationError):
        task.provision('data', record)
    assert state.calls == []
    assert not container.exists()


@pytest.mark.parametrize(('field', 'value'), [
    ('machine_id', 'another-machine'), ('volume', 'other-volume'),
    ('host', 'other-host'),
    ('container', '/var/lib/other-container.luks'), ('primary_escrow', None),
    ('emergency_export', None), ('recovery_passphrase', 'invalid'),
    ('origin', 'existing'),
])
def test_passphrase_provision_rejects_invalid_identity_or_custody_before_allocation(
    passphrase_provision, field, value
):
    task, record, state, container = passphrase_provision
    record[field] = value
    with pytest.raises(migration.MigrationError):
        task.provision('data', record)
    assert state.calls == []
    assert not container.exists()
    assert not Path(str(container) + '.allocating').exists()


@pytest.mark.parametrize('obstacle', [
    'mapping', 'container', 'pending-receipt', 'completed-receipt'])
def test_passphrase_provision_preserves_conflicting_existing_state(
    passphrase_provision, obstacle
):
    task, record, state, container = passphrase_provision
    if obstacle == 'mapping':
        existing = Path(task.config['volumes']['data']['device'])
        existing.write_bytes(b'occupied mapping')
    elif obstacle == 'container':
        existing = container
        existing.write_bytes(b'existing storage without provisioning ownership')
    else:
        suffix = ('.luks.provisioning.json' if obstacle == 'pending-receipt'
                  else '.luks.provisioned.json')
        existing = container.with_suffix(suffix)
        existing.write_text(json.dumps({'machine_id': 'another-machine'}))
    before = existing.read_bytes()
    with pytest.raises(migration.MigrationError):
        task.provision('data', record)
    assert existing.read_bytes() == before
    assert not any(c[:2] == ('cryptsetup', 'luksFormat') or c[0] == 'mkfs.ext4'
                   for c in state.calls)


def test_passphrase_provision_rejects_an_unexpected_filesystem_on_resume(
    passphrase_provision
):
    task, record, state, container = passphrase_provision
    state.fail = 'mkfs'
    with pytest.raises(migration.MigrationError):
        task.provision('data', record)
    state.fail = None
    state.fs = True
    state.filesystem = 'xfs'
    before = len(state.calls)
    with pytest.raises(migration.MigrationError, match='filesystem'):
        task.provision('data', record)
    assert not any(c[:2] == ('cryptsetup', 'luksFormat') or c[0] == 'mkfs.ext4'
                   for c in state.calls[before:])
    assert not container.with_suffix('.luks.provisioned.json').exists()


def test_passphrase_provision_never_recreates_filesystem_after_completed_receipt(
    passphrase_provision
):
    task, record, state, _ = passphrase_provision
    task.provision('data', record)
    state.fs = False
    before = len(state.calls)
    with pytest.raises(migration.MigrationError, match='filesystem'):
        task.provision('data', record)
    assert not any(c[:2] == ('cryptsetup', 'luksFormat') or c[0] == 'mkfs.ext4'
                   for c in state.calls[before:])


@pytest.fixture
def passphrase_layout(tmp_path, monkeypatch):
    container = tmp_path / "data.luks"
    container.write_bytes(b"preserved encrypted volume")
    task = migration.Migration({"unlockMethod": "passphrase",
        "volumes": {"data": {"container": str(container), "device": "/dev/mapper/test-never-created"}}},
        SimpleNamespace(_require_protected_swap=lambda: None))
    return container, task


def test_passphrase_boot_prompt_reuses_cached_answer_first(passphrase_layout, monkeypatch):
    container, task = passphrase_layout
    calls = []
    def run(*args, **kwargs):
        calls.append((args, kwargs.get("input")))
        return b"shared-test-passphrase\n" if args[0] == "systemd-ask-password" else b""
    monkeypatch.setattr(migration, "run", run)
    task.unlock("data")
    assert [c[0] for c in calls] == [
        ("cryptsetup", "isLuks", str(container)),
        ("systemd-ask-password", "--timeout=0", "--keyname=luxnix-operator-storage", "--accept-cached",
         "Unlock test-never-created:"),
        ("cryptsetup", "open", "--type", "luks", "--key-file=-", str(container), "test-never-created"),
    ]
    # The passphrase reaches cryptsetup on stdin only, never as an argument.
    assert calls[-1][1] == b"shared-test-passphrase"
    assert container.read_bytes() == b"preserved encrypted volume"


def test_passphrase_boot_prompt_asks_again_after_wrong_answer(passphrase_layout, monkeypatch):
    container, task = passphrase_layout
    answers = iter([b"stale-cached\n", b"typo\n", b"correct\n"])
    asks = []
    def run(*args, input=None, **kwargs):
        if args[0] == "systemd-ask-password":
            asks.append(args)
            return next(answers)
        if args[1] == "open" and input != b"correct":
            raise migration.MigrationError("cryptsetup failed")
        return b""
    monkeypatch.setattr(migration, "run", run)
    task.unlock("data")
    assert ["--accept-cached" in a for a in asks] == [True, False, False]


def test_passphrase_boot_prompt_fails_closed_after_attempts(passphrase_layout, monkeypatch):
    _, task = passphrase_layout
    asks = []
    def run(*args, **kwargs):
        if args[0] == "systemd-ask-password":
            asks.append(args)
            return b"wrong\n"
        if args[1] == "open":
            raise migration.MigrationError("cryptsetup failed")
        return b""
    monkeypatch.setattr(migration, "run", run)
    with pytest.raises(migration.MigrationError, match="No valid passphrase"):
        task.unlock("data")
    assert len(asks) == migration.PASSPHRASE_ATTEMPTS


def test_key_file_unlock_uses_installed_key_and_never_prompts(tmp_path, monkeypatch):
    key, container = tmp_path / "key", tmp_path / "container"
    key.write_bytes(b"enrolled key")
    key.chmod(0o400)
    calls = []
    monkeypatch.setattr(migration, "run", lambda *args, **kwargs: calls.append(args) or b"")
    migration.Migration.unlock_with_key_file(str(key), container, "luxnix-app-storage")
    assert calls == [("cryptsetup", "open", "--type", "luks", f"--key-file={key}", str(container), "luxnix-app-storage")]
    assert not any("systemd-ask-password" in call for call in calls)


@pytest.mark.parametrize("problem", ["missing", "readable", "rejected"])
def test_key_file_unlock_failures_name_the_recovery_command(tmp_path, monkeypatch, problem):
    key, container = tmp_path / "key", tmp_path / "container"
    if problem != "missing":
        key.write_bytes(b"enrolled key")
        key.chmod(0o444 if problem == "readable" else 0o400)

    def run(*args, **kwargs):
        if problem == "rejected":
            raise migration.MigrationError("cryptsetup failed (exit 2); sources retained")
        return b""

    monkeypatch.setattr(migration, "run", run)
    with pytest.raises(migration.MigrationError, match="luxnix-operator-storage open luxnix-app-storage"):
        migration.Migration.unlock_with_key_file(str(key), container, "luxnix-app-storage")
