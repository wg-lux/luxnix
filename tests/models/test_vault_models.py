import unittest
from lx_administration.models.vault.hosts import VaultClient, HostConfig
from .mock_data.generators import mock_vault_client, mock_host_config


class TestVaultModels(unittest.TestCase):
    def test_vault_client_creation(self):
        client = mock_vault_client()
        self.assertIsInstance(client, VaultClient)
        # ...additional assertions...

    def test_host_config_creation(self):
        host_config = mock_host_config()
        self.assertIsInstance(host_config, HostConfig)
        self.assertEqual(host_config.ip_address, "192.168.0.1")
        # ...additional assertions...


if __name__ == "__main__":
    unittest.main()
