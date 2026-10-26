"""Recovery custody uses real Ansible encryption and disposable synthetic data."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
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
