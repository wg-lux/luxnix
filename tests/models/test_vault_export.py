from unittest.mock import MagicMock, patch

import pytest

from lx_administration.models.ansible import AnsibleInventory
from lx_administration.models.vault import PreSharedKey, Vault


def test_export_secrets_by_client_reencrypts_each_secret(tmp_path):
    inventory = MagicMock(spec=AnsibleInventory)
    inventory.get_hostnames.return_value = ["client", None]
    vault = Vault(dir=str(tmp_path), inventory=inventory)

    psk_file = tmp_path / "client.psk"
    psk_file.write_text("pre-shared-key", encoding="utf-8")
    psk = PreSharedKey(name="client", file=str(psk_file))

    secret = MagicMock()
    secret.name = "database-password"
    secret.target_name = "database-password.yml"
    logger = MagicMock()

    with (
        patch.object(Vault, "get_client_psk", return_value=psk) as get_client_psk,
        patch.object(Vault, "get_host_secrets", return_value=[secret]) as get_secrets,
    ):
        vault.export_secrets_by_client(logger=logger)

    get_client_psk.assert_called_once_with("client", logger)
    get_secrets.assert_called_once_with("client", logger)
    secret.create_re_encrypted_file.assert_called_once_with(
        str(tmp_path / "deploy/client/database-password.yml"),
        str(psk_file),
        vault,
    )


def test_export_requires_inventory_before_replacing_deploy_directory(tmp_path):
    deploy_dir = tmp_path / "deploy"
    deploy_dir.mkdir()
    marker = deploy_dir / "existing-secret"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="Inventory must be loaded"):
        Vault(dir=str(tmp_path)).export_secrets_by_client(logger=MagicMock())

    assert marker.read_text(encoding="utf-8") == "keep"
