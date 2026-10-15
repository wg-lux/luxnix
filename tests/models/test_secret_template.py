from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from lx_administration.models.ansible import AnsibleInventory
from lx_administration.models.vault import SecretTemplate, Vault
from lx_administration.password import PasswordGenerator


def _vault(tmp_path, *hostnames):
    inventory = MagicMock(spec=AnsibleInventory)
    inventory.all = [SimpleNamespace(hostname=name) for name in hostnames]
    return Vault(dir=str(tmp_path), inventory=inventory)


def test_secret_generator_selection_is_explicit():
    passphrase = SecretTemplate(
        name="user", owner_type="local", secret_type="password"
    ).get_secret_generator()
    system_password = SecretTemplate(
        name="service", owner_type="services", secret_type="system_password"
    ).get_secret_generator()

    assert passphrase.mode == "passphrase"
    assert system_password.mode == "password"


def test_create_secret_template_initializes_directory_and_generator(tmp_path):
    template = SecretTemplate.create_secret_template(
        name="admin",
        owner_type="local",
        vault_dir=tmp_path,
    )

    assert template.directory == str(tmp_path / "secrets/password/local/admin")
    assert template.generator is not None
    assert template.generator.mode == "passphrase"


def test_secret_generator_rejects_unknown_type():
    template = SecretTemplate(name="invalid", owner_type="local", secret_type="unknown")

    with pytest.raises(ValueError, match="Invalid secret_type: unknown"):
        template.get_secret_generator()


def test_template_validation_requires_a_real_directory(tmp_path):
    template = SecretTemplate(
        name="user",
        owner_type="local",
        directory=str(tmp_path / "missing"),
    )

    with pytest.raises(ValueError, match="does not exist"):
        template.assert_valid()


def test_secret_creation_requires_inventory(tmp_path):
    template = SecretTemplate(
        name="admin",
        owner_type="local",
        directory=str(tmp_path),
        generator=PasswordGenerator(mode="password"),
    )

    with pytest.raises(ValueError, match="Inventory must be loaded"):
        template.create_or_update_secrets(Vault(dir=str(tmp_path)))


@patch("lx_administration.models.vault.secret_template.Secret.create_secret")
@patch("lx_administration.models.vault.secret_template.Secret.check_exists")
def test_secret_creation_reports_changes_and_removes_hostname_from_target(
    check_exists, create_secret, tmp_path
):
    check_exists.return_value = False
    generator = PasswordGenerator(mode="password")
    template = SecretTemplate(
        name="admin@gc-02",
        owner_type="local",
        directory=str(tmp_path),
        generator=generator,
    )
    vault = _vault(tmp_path, "gc-02")
    logger = MagicMock()

    with patch.object(
        PasswordGenerator,
        "pipe",
        return_value=[("password", "TOP_SECRET")],
    ):
        changed = template.create_or_update_secrets(vault, logger=logger)

    assert changed is True
    assert template.secret_names == ["admin@gc-02_password"]
    assert vault.secrets[0].target_name == "SCRT_local_password_admin_password"
    create_secret.assert_called_once_with(
        secret="TOP_SECRET",
        file=str(tmp_path / "admin@gc-02_password"),
        vault=vault,
    )
    assert "TOP_SECRET" not in str(logger.mock_calls)


@patch("lx_administration.models.vault.secret_template.Secret.check_exists")
def test_secret_creation_reports_no_change_for_existing_secrets(check_exists, tmp_path):
    check_exists.return_value = True
    generator = PasswordGenerator(mode="password")
    template = SecretTemplate(
        name="existing",
        owner_type="local",
        directory=str(tmp_path),
        generator=generator,
    )
    vault = _vault(tmp_path)

    with patch.object(
        PasswordGenerator,
        "pipe",
        return_value=[("password", "discarded")],
    ):
        changed = template.create_or_update_secrets(vault)

    assert changed is False
    assert vault.secrets == []
