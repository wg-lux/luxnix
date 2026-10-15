import pytest

from lx_administration.models.vault import Vault


def test_require_inventory_reports_missing_configuration():
    with pytest.raises(ValueError, match="Inventory must be loaded"):
        Vault()._require_inventory()
