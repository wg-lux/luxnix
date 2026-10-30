import pytest

from lx_administration.models.vault import PreSharedKey, Secret, SecretTemplate, Vault


def _secret(name: str = "database", target_name: str = "database.yml") -> Secret:
    return Secret(
        name=name,
        file=f"/tmp/{name}.secret",
        owner_type="roles",
        template_name="database-role",
        target_name=target_name,
    )


def test_get_secret_by_target_name_returns_required_secret():
    secret = _secret()
    vault = Vault(secrets=[secret])

    assert vault.get_secret_by_target_name("database.yml") is secret


def test_get_secret_by_target_name_rejects_missing_secret():
    with pytest.raises(ValueError, match="Secret 'missing.yml' not found"):
        Vault().get_secret_by_target_name("missing.yml")


def test_get_template_secrets_rejects_missing_template():
    with pytest.raises(ValueError, match="Template 'missing' not found"):
        Vault()._get_template_secrets("missing")


def test_get_template_secrets_rejects_missing_referenced_secret():
    template = SecretTemplate(
        name="database-role",
        owner_type="roles",
        secret_names=["missing"],
    )

    with pytest.raises(
        ValueError,
        match="Secret 'missing' referenced by template 'database-role' not found",
    ):
        Vault(secret_templates=[template])._get_template_secrets("database-role")


def test_get_local_vault_id_with_path_requires_local_psk():
    vault = Vault(local_hostname_override="client")

    with pytest.raises(ValueError, match="Local PSK not found"):
        vault.get_local_vault_id_with_path()


def test_get_local_vault_id_with_path_includes_psk_file(tmp_path):
    psk_file = tmp_path / "client.psk"
    psk_file.write_text("key", encoding="utf-8")
    psk = PreSharedKey(name="client", file=str(psk_file))
    vault = Vault(local_hostname_override="client", pre_shared_keys=[psk])

    assert vault.get_local_vault_id_with_path() == f"client@{psk_file}"
