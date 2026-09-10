import stat
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from lx_administration.models.vault import PreSharedKey, Secret, Vault
from lx_administration.models.vault.secret import decrypt_secret


@pytest.fixture
def vault(tmp_path):
    key = tmp_path / "master.key"
    key.write_text("synthetic-master-key")
    key.chmod(0o600)
    return Vault(key=str(key))


def _secret(file_path: Path, value: str | None = "replacement") -> Secret:
    return Secret(
        name="example",
        file=str(file_path),
        owner_type="local",
        template_name="example",
        target_name="SCRT_example",
        value=value,
    )


def test_create_secret_publishes_only_ciphertext(tmp_path, vault):
    target = tmp_path / "nested/secret"
    assert Secret.create_secret("TOP_SECRET", target, vault) == "TOP_SECRET"
    assert b"TOP_SECRET" not in target.read_bytes()
    assert decrypt_secret(target, vault.key) == b"TOP_SECRET"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not list(target.parent.glob(f".{target.name}.*"))


def test_failed_update_preserves_last_encrypted_file(tmp_path, vault):
    target = tmp_path / "secret"
    Secret.create_secret("previous", target, vault)
    previous = target.read_bytes()
    with patch(
        "lx_administration.models.vault.secret._encrypt_bytes",
        side_effect=ValueError("encryption failed"),
    ):
        with pytest.raises(ValueError, match="encryption failed"):
            _secret(target).update_file_encryption(vault)
    assert target.read_bytes() == previous
    assert not list(tmp_path.glob(f".{target.name}.*"))


def test_update_requires_a_value(tmp_path, vault):
    with pytest.raises(ValueError, match="Secret.value is not set"):
        _secret(tmp_path / "secret", value=None).update_file_encryption(vault)


def test_check_exists_requires_matching_file_and_metadata(tmp_path, vault):
    target = tmp_path / "secret"
    secret = _secret(target)
    assert Secret.check_exists(secret.name, target, vault) is False
    target.write_text("encrypted")
    with pytest.warns(UserWarning, match="file=True, metadata=False"):
        assert Secret.check_exists(secret.name, target, vault) is False
    vault.secrets.append(secret)
    assert Secret.check_exists(secret.name, target, vault) is True


def test_rekey_publishes_private_file_only_after_success(tmp_path, vault):
    source = tmp_path / "source"
    Secret.create_secret("secret", source, vault)
    psk = tmp_path / "client.psk"
    psk.write_text("synthetic-psk")
    psk.chmod(0o600)
    vault.pre_shared_keys = [PreSharedKey(name="client", file=str(psk))]
    target = tmp_path / "deploy/client/SCRT_example"
    assert _secret(source).create_re_encrypted_file(target, psk, vault) == target
    assert decrypt_secret(target, psk, "client") == b"secret"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700


def test_failed_rekey_preserves_previous_export(tmp_path, vault):
    source = tmp_path / "source"
    Secret.create_secret("secret", source, vault)
    target = tmp_path / "export"
    target.write_text("LAST_GOOD_EXPORT")
    with pytest.raises(ValueError, match="registered identity"):
        _secret(source).create_re_encrypted_file(target, tmp_path / "missing", vault)
    assert target.read_text() == "LAST_GOOD_EXPORT"
    assert not list(tmp_path.glob(f".{target.name}.*"))


def test_validate_secret_accepts_current_encrypted_file(tmp_path):
    target = tmp_path / "secret"
    target.write_text("encrypted")
    secret = _secret(target)
    secret.created = datetime(2026, 1, 1)
    secret.updated = datetime(2026, 2, 1)
    secret.validity = timedelta(days=30)
    secret.validate_secret(now=datetime(2026, 3, 1))


def test_validate_secret_rejects_expired_metadata(tmp_path):
    secret = _secret(tmp_path / "secret")
    secret.created = datetime(2026, 1, 1)
    secret.validity = timedelta(days=30)
    with pytest.raises(ValueError, match="outside its validity window"):
        secret.validate_secret(now=datetime(2026, 2, 1))


def test_validate_secret_does_not_turn_missing_file_into_directory(tmp_path):
    target = tmp_path / "missing-secret"
    secret = _secret(target)
    secret.created = datetime(2026, 1, 1)
    with pytest.raises(FileNotFoundError, match="Encrypted secret file not found"):
        secret.validate_secret(now=datetime(2026, 1, 2))
    assert not target.exists()


def test_validate_secret_requires_created_timestamp(tmp_path):
    with pytest.raises(ValueError, match="Secret.created is not set"):
        _secret(tmp_path / "secret").validate_secret(now=datetime(2026, 1, 1))
