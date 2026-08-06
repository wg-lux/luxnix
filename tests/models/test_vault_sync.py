from unittest.mock import MagicMock, call, patch

import pytest

from lx_administration.models.ansible import AnsibleInventory
from lx_administration.models.vault import SecretTemplate, Vault


def test_load_inventory_rejects_missing_file(tmp_path):
    missing = tmp_path / "missing.yml"

    with pytest.raises(
        FileNotFoundError, match=f"Inventory file does not exist: {missing}"
    ):
        Vault().load_inventory(missing)


def test_sync_secret_templates_uses_side_effect_helpers():
    inventory = MagicMock(spec=AnsibleInventory)
    inventory.get_role_names.return_value = ["web"]
    inventory.get_group_names.return_value = ["production"]
    inventory.get_hostnames.return_value = []
    vault = Vault(inventory=inventory)

    template = MagicMock(spec=SecretTemplate)
    vault.secret_templates = [template]
    logger = MagicMock()

    with patch.object(
        Vault,
        "get_or_create_secret_templates",
        return_value=([], []),
    ) as get_or_create:
        vault.sync_secret_templates(logger=logger)

    assert get_or_create.call_args_list == [
        call(["web"], "roles", secret_type="system_password"),
        call(["production"], "groups", secret_type="system_password"),
    ]
    template.assert_valid.assert_called_once_with()
    template.create_or_update_secrets.assert_called_once_with(
        vault=vault,
        logger=logger,
    )
