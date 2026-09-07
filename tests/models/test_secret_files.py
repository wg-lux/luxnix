import stat
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lx_administration.models.vault import Secret, Vault


def _vault(vault_id: str | None = "example") -> MagicMock:
    vault = MagicMock(spec=Vault)
    vault.get_local_vault_id.return_value = vault_id
    vault.secrets = []
    return vault


def _secret(file_path: Path, value: str | None = "replacement") -> Secret:
    return Secret(
        name="example",
        file=str(file_path),
        owner_type="local",
        template_name="example",
        target_name="SCRT_example",
        value=value,
    )


@patch("lx_administration.models.vault.secret.subprocess.run")
def test_create_secret_replaces_target_only_after_encryption(run, tmp_path):
    target = tmp_path / "nested/secret"

    result = Secret.create_secret("TOP_SECRET", target, _vault())

    assert result == "TOP_SECRET"
    assert target.read_text(encoding="utf-8") == "TOP_SECRET"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    command = run.call_args.args[0]
    assert command[:3] == [
        "ansible-vault",
        "encrypt",
        "--encrypt-vault-id=example",
    ]
    assert command[3] != str(target)
    assert not list(target.parent.glob(f".{target.name}.*"))


@patch("lx_administration.models.vault.secret.subprocess.run")
def test_failed_update_preserves_last_encrypted_file(run, tmp_path):
    target = tmp_path / "secret"
    target.write_text("LAST_KNOWN_ENCRYPTED", encoding="utf-8")
    run.side_effect = subprocess.CalledProcessError(1, ["ansible-vault"])

    with pytest.raises(subprocess.CalledProcessError):
        _secret(target).update_file_encryption(_vault())

    assert target.read_text(encoding="utf-8") == "LAST_KNOWN_ENCRYPTED"
    assert not list(tmp_path.glob(f".{target.name}.*"))


def test_update_requires_a_value_and_vault_id(tmp_path):
    target = tmp_path / "secret"

    with pytest.raises(ValueError, match="Secret.value is not set"):
        _secret(target, value=None).update_file_encryption(_vault())
    with pytest.raises(ValueError, match="Vault ID not found"):
        _secret(target).update_file_encryption(_vault(vault_id=None))


def test_check_exists_requires_matching_file_and_metadata(tmp_path):
    target = tmp_path / "secret"
    secret = _secret(target)
    vault = _vault()

    assert Secret.check_exists(secret.name, str(target), vault) is False

    target.write_text("encrypted", encoding="utf-8")
    with pytest.warns(UserWarning, match="file=True, metadata=False"):
        assert Secret.check_exists(secret.name, str(target), vault) is False

    vault.secrets.append(secret)
    assert Secret.check_exists(secret.name, str(target), vault) is True


@patch("lx_administration.models.vault.secret.subprocess.run")
def test_rekey_publishes_private_file_only_after_success(run, tmp_path):
    source = tmp_path / "source"
    source.write_text("SOURCE_ENCRYPTED", encoding="utf-8")
    psk = tmp_path / "client.psk"
    psk.write_text("psk", encoding="utf-8")
    target = tmp_path / "deploy/client/SCRT_example"

    published = _secret(source).create_re_encrypted_file(target, psk, _vault())

    assert published == target
    assert target.read_text(encoding="utf-8") == "SOURCE_ENCRYPTED"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    command = run.call_args.args[0]
    assert command[:4] == [
        "ansible-vault",
        "rekey",
        "--new-vault-password-file",
        str(psk),
    ]
    assert command[4] != str(target)
    assert not list(target.parent.glob(f".{target.name}.*"))


@patch("lx_administration.models.vault.secret.subprocess.run")
def test_failed_rekey_preserves_previous_export_and_redacts_stderr(run, tmp_path):
    source = tmp_path / "source"
    source.write_text("SOURCE_ENCRYPTED", encoding="utf-8")
    psk = tmp_path / "client.psk"
    psk.write_text("psk", encoding="utf-8")
    target = tmp_path / "deploy/SCRT_example"
    target.parent.mkdir()
    target.write_text("LAST_GOOD_EXPORT", encoding="utf-8")
    run.side_effect = subprocess.CalledProcessError(
        4,
        ["ansible-vault"],
        stderr="TOP_SECRET_DIAGNOSTIC",
    )

    with pytest.warns(UserWarning, match="will be overwritten"):
        with pytest.raises(RuntimeError, match="ansible-vault exit 4") as error:
            _secret(source).create_re_encrypted_file(str(target), str(psk), _vault())

    assert "TOP_SECRET_DIAGNOSTIC" not in str(error.value)
    assert target.read_text(encoding="utf-8") == "LAST_GOOD_EXPORT"
    assert not list(target.parent.glob(f".{target.name}.*"))


def test_validate_secret_accepts_current_encrypted_file(tmp_path):
    target = tmp_path / "secret"
    target.write_text("encrypted", encoding="utf-8")
    secret = _secret(target)
    secret.created = datetime(2026, 1, 1)
    secret.updated = datetime(2026, 2, 1)
    secret.validity = timedelta(days=30)

    secret.validate_secret(now=datetime(2026, 3, 1))


def test_validate_secret_rejects_expired_metadata(tmp_path):
    target = tmp_path / "secret"
    target.write_text("encrypted", encoding="utf-8")
    secret = _secret(target)
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
    secret = _secret(tmp_path / "secret")

    with pytest.raises(ValueError, match="Secret.created is not set"):
        secret.validate_secret(now=datetime(2026, 1, 1))
