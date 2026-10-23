import runpy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from lx_administration.models.vault import Vault, admin_passwords
from lx_administration.models.vault.admin_passwords import (
    import_admin_passwords,
    load_admin_passwords,
)
from lx_administration.models.vault.secret import Secret
from lx_administration.models.vault.secret_template import SecretTemplate

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_admin_password_loader_normalizes_names_and_ignores_null(tmp_path):
    source = tmp_path / "passwords.yml"
    source.write_text(
        "admin_passwords:\n  10: numeric-name\n  skipped: null\n",
        encoding="utf-8",
    )

    assert load_admin_passwords(source) == {"10": "numeric-name"}


def test_admin_password_loader_reports_missing_source(tmp_path):
    source = tmp_path / "missing.yml"

    with pytest.raises(FileNotFoundError) as error:
        load_admin_passwords(source)

    assert str(source) in str(error.value)


@pytest.mark.parametrize("content", ["", "admin_passwords: null\n"])
def test_admin_password_loader_accepts_empty_sources(tmp_path, content):
    source = tmp_path / "passwords.yml"
    source.write_text(content, encoding="utf-8")

    assert load_admin_passwords(str(source)) == {}


def test_admin_password_loader_rejects_duplicate_hosts_with_path(tmp_path):
    source = tmp_path / "passwords.yml"
    source.write_text(
        "admin_passwords:\n  gc-02: first\n  gc-02: shadowed\n",
        encoding="utf-8",
    )

    with pytest.raises(yaml.YAMLError, match="duplicate key 'gc-02'") as error:
        load_admin_passwords(source)

    assert str(source) in str(error.value)


def test_vault_clis_share_loader_and_never_report_plaintext_values():
    bootstrap = (REPO_ROOT / "scripts/bootstrap-lx-vault.py").read_text(
        encoding="utf-8"
    )
    validator = (REPO_ROOT / "scripts/validate-admin-passwords.py").read_text(
        encoding="utf-8"
    )

    for source in (bootstrap, validator):
        assert "load_admin_passwords" in source
        assert "models.vault.admin_passwords import" not in source
        assert "yaml.safe_load" not in source
    assert "plaintext password mismatch" in validator
    assert "vault='{stored_password}'" not in validator
    assert "file='{password}'" not in validator
    assert "proc.stderr.strip() or proc.stdout.strip()" not in validator


def test_decrypt_failure_does_not_expose_process_output(tmp_path, monkeypatch):
    namespace = runpy.run_path(str(REPO_ROOT / "scripts/validate-admin-passwords.py"))
    encrypted = tmp_path / "secret"
    encrypted.touch()

    def failed_decryption(*args, **kwargs):
        raise ValueError("TOP_SECRET_STDOUT TOP_SECRET_STDERR")

    monkeypatch.setitem(
        namespace["_decrypt_secret"].__globals__, "decrypt_secret", failed_decryption
    )

    with pytest.raises(RuntimeError) as error:
        namespace["_decrypt_secret"](
            encrypted,
            "test-vault-id",
            tmp_path / "vault.key",
        )

    assert "TOP_SECRET_STDOUT" not in str(error.value)
    assert "TOP_SECRET_STDERR" not in str(error.value)
    assert "declared master key" in str(error.value)


def test_admin_password_import_uses_vault_directory_for_unset_template(
    tmp_path,
    monkeypatch,
):
    vault = Vault(dir=tmp_path.as_posix())
    template = SecretTemplate(
        name="admin@client",
        owner_type="local",
        secret_type="password",
        directory=None,
    )
    created_secrets = []

    monkeypatch.setattr(
        Vault,
        "get_or_create_secret_template",
        lambda self, **kwargs: (template, False),
    )
    monkeypatch.setattr(
        admin_passwords.PasswordGenerator,
        "create_password_hash",
        lambda self, password: "HASH",
    )
    monkeypatch.setattr(
        Secret,
        "create_secret",
        staticmethod(
            lambda secret, file, vault: created_secrets.append((secret, file))
        ),
    )

    import_admin_passwords(
        vault,
        {"client": "TOP_SECRET"},
        logger=MagicMock(),
    )

    expected_dir = tmp_path / "secrets/password/local/admin@client"
    assert template.directory == expected_dir.as_posix()
    assert created_secrets == [
        ("TOP_SECRET", expected_dir / "admin@client_password"),
        ("HASH", expected_dir / "admin@client_password_hash"),
    ]
    assert [secret.target_name for secret in vault.secrets] == [
        "SCRT_local_password_admin_password",
        "SCRT_local_password_admin_password_hash",
    ]
    assert template.secret_names == [
        "admin@client_password",
        "admin@client_password_hash",
    ]


def test_admin_password_import_clears_value_after_update_failure(
    tmp_path,
    monkeypatch,
):
    template = SecretTemplate(
        name="admin@client",
        owner_type="local",
        directory=tmp_path.as_posix(),
        secret_names=["admin@client_password"],
    )
    existing = Secret(
        name="admin@client_password",
        template_name=template.name,
        file=(tmp_path / "admin@client_password").as_posix(),
        target_name="SCRT_local_password_admin_password",
        owner_type="local",
    )
    vault = Vault(dir=tmp_path.as_posix(), secrets=[existing])

    monkeypatch.setattr(
        Vault,
        "get_or_create_secret_template",
        lambda self, **kwargs: (template, False),
    )
    monkeypatch.setattr(
        admin_passwords,
        "_admin_secret_values",
        lambda password, generator: (("password", password),),
    )
    monkeypatch.setattr(
        Secret,
        "update_file_encryption",
        lambda self, vault: (_ for _ in ()).throw(RuntimeError("encrypt failed")),
    )

    with pytest.raises(RuntimeError, match="encrypt failed"):
        import_admin_passwords(
            vault,
            {"client": "TOP_SECRET"},
            logger=MagicMock(),
        )

    assert existing.value is None
    assert existing.updated is not None
