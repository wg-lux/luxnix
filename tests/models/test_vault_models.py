import unittest
from unittest.mock import patch, MagicMock, ANY
from pathlib import Path
from datetime import datetime, timedelta
from lx_administration.models import Vault
from lx_administration.models.vault import (
    SecretTemplate,
    PreSharedKey,
    Secret,
)
from lx_administration.models.ansible import AnsibleInventory
import os
import shutil


class TestVaultModel(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.test_dir = "/tmp/test_vault"
        self.test_key = "/tmp/test_vault.key"
        self.vault = Vault(dir=self.test_dir, key=self.test_key)
        Path(self.test_dir).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up after each test method."""
        # Clean up any created files/directories
        test_dir_path = Path(self.test_dir)
        if test_dir_path.exists():
            shutil.rmtree(test_dir_path)

        test_key_path = Path(self.test_key)
        if test_key_path.exists():
            test_key_path.unlink()

    def test_get_vault_paths(self):
        """Test _get_vault_paths method returns correct Path objects."""
        dir_path, key_path, vault_path = Vault._get_vault_paths(
            self.test_dir, self.test_key
        )

        self.assertIsInstance(dir_path, Path)
        self.assertIsInstance(key_path, Path)
        self.assertIsInstance(vault_path, Path)
        self.assertEqual(vault_path, Path(self.test_dir) / "vault.yml")

    @patch("socket.gethostname")
    def test_get_local_vault_id(self, mock_gethostname):
        """Test get_local_vault_id returns correct hostname."""
        mock_gethostname.return_value = "test-host"
        self.assertEqual(self.vault.get_local_vault_id(), "test-host")

    @patch("pathlib.Path.exists")
    @patch("lx_administration.models.vault.PreSharedKey.generate")
    def test_get_or_create_psk(self, mock_generate, mock_exists):
        """Test get_or_create_psk method."""
        mock_exists.return_value = True
        mock_psk = PreSharedKey(
            name="test-host",
            file=str(Path(self.test_dir) / "psk" / "test.psk"),
            created=datetime.now(),
            updated=datetime.now(),
            validity=timedelta(days=30),
        )
        mock_generate.return_value = mock_psk

        # Test creating new PSK
        psk, created = self.vault.get_or_create_psk("test-host")
        self.assertTrue(created)
        self.assertEqual(psk.name, "test-host")
        self.assertIn(psk, self.vault.pre_shared_keys)

        # Test retrieving existing PSK
        psk2, created = self.vault.get_or_create_psk("test-host")
        self.assertFalse(created)
        self.assertEqual(psk2, psk)

    def test_get_host_secrets(self):
        """Test get_host_secrets method."""
        # Create mock inventory and host
        mock_host = MagicMock()
        mock_host.hostname = "test-host"
        mock_host.ansible_role_names = ["role1"]
        mock_host.ansible_group_names = ["group1"]

        mock_inventory = MagicMock(spec=AnsibleInventory)
        mock_inventory.get_host_by_name.return_value = mock_host
        self.vault.inventory = mock_inventory

        # Create test templates and secrets
        role_template = SecretTemplate(
            name="role1",
            owner_type="roles",
            secret_type="password",
            secret_names=["role1_secret"],  # Add this line
        )
        role_secret = Secret(
            name="role1_secret",
            file="/tmp/role1.secret",
            owner_type="roles",
            template_name="role1",
            target_name="role1_target",
        )

        local_template = SecretTemplate(
            name="user@test-host",
            owner_type="local",
            secret_type="password",
            secret_names=["user@test-host_secret"],  # Add this line
        )
        local_secret = Secret(
            name="user@test-host_secret",
            file="/tmp/local.secret",
            owner_type="local",
            template_name="user@test-host",
            target_name="local_target",
        )

        self.vault.secret_templates.extend([role_template, local_template])
        self.vault.secrets.extend([role_secret, local_secret])

        # Test getting host secrets
        host_secrets = self.vault.get_host_secrets("test-host")
        self.assertEqual(len(host_secrets), 2)
        self.assertIn(role_secret, host_secrets)
        self.assertIn(local_secret, host_secrets)

    @patch("pathlib.Path.exists")
    @patch("builtins.open")
    @patch("yaml.safe_load")
    def test_load_dir(self, mock_yaml_load, mock_open, mock_exists):
        """Test load_dir method with mocked file operations."""
        # Setup mocks
        mock_exists.return_value = True

        # Create a minimal valid vault data structure
        mock_vault_data = {
            "secrets": [],
            "access_keys": [],
            "secret_templates": [],
            "pre_shared_keys": [],
            "dir": self.test_dir,
            "key": self.test_key,
            "owner_types": ["local", "roles", "services", "luxnix", "clients"],
            "secret_types": ["password", "key", "certificate"],
            "default_system_users": ["admin"],
            "subnet": "172.16.255.",
        }

        mock_yaml_load.return_value = mock_vault_data

        # Now test the load_dir method
        vault = Vault.load_dir(self.test_dir, self.test_key)

        self.assertIsInstance(vault, Vault)
        self.assertEqual(len(vault.secrets), 0)
        self.assertEqual(len(vault.access_keys), 0)
        self.assertEqual(vault.dir, self.test_dir)
        self.assertEqual(vault.key, self.test_key)

    @patch("pathlib.Path.exists")
    def test_load_dir_file_not_found(self, mock_exists):
        """Test load_dir method raises FileNotFoundError when files don't exist."""
        mock_exists.return_value = False
        with self.assertRaises(FileNotFoundError):
            Vault.load_dir(self.test_dir, self.test_key)

    def test_summary(self):
        """Test summary method returns correct string format."""
        summary = self.vault.summary()
        self.assertIsInstance(summary, str)
        self.assertIn("Vault Summary:", summary)
        self.assertIn("Secrets: 0", summary)
        self.assertIn("Secret Templates: 0", summary)
        self.assertIn("Pre-Shared Keys: 0", summary)
        # Removed Access Keys check since it's no longer part of the model

    @patch("lx_administration.models.vault.manager.dump_yaml")
    def test_save_to_file(self, mock_dump_yaml):
        """Test save_to_file method."""
        # Create the test directory
        Path(self.test_dir).mkdir(parents=True, exist_ok=True)

        # Expected data structure that should be passed to dump_yaml
        expected_data = {
            "secrets": [],
            "dir": self.test_dir,
            "key": self.test_key,
            "ansible_cfg_path": "./conf/ansible.cfg",
            "owner_types": self.vault.owner_types,
            "secret_types": self.vault.secret_types,
            "default_client_secret_types": self.vault.default_client_secret_types,
            "default_local_secret_types": self.vault.default_local_secret_types,
            "default_system_users": self.vault.default_system_users,
            "subnet": self.vault.subnet,
            "secret_templates": [],
            "pre_shared_keys": [],
        }

        # Call the method under test
        self.vault.save_to_file()

        # Verify dump_yaml was called correctly
        mock_dump_yaml.assert_called_once()
        actual_data = mock_dump_yaml.call_args[0][0]  # First positional argument
        self.assertEqual(actual_data, expected_data)

    def test_get_secret_template_by_name(self):
        """Test get_secret_template_by_name method."""
        template = SecretTemplate(
            name="test",
            owner_type=self.vault.owner_types[0],
            secret_type=self.vault.secret_types[0],
        )
        self.vault.secret_templates.append(template)

        result = self.vault.get_secret_template_by_name("test")
        self.assertEqual(result, template)

        result = self.vault.get_secret_template_by_name("nonexistent")
        self.assertIsNone(result)

    @patch("lx_administration.models.vault.SecretTemplate.create_secret_template")
    def test_get_or_create_secret_template(self, mock_create):
        """Test get_or_create_secret_template method."""
        mock_template = SecretTemplate(
            name="test",
            owner_type=self.vault.owner_types[0],
            secret_type=self.vault.secret_types[0],
        )
        mock_create.return_value = mock_template

        # Test creation of new template
        template, created = self.vault.get_or_create_secret_template(
            "test", self.vault.owner_types[0], self.vault.secret_types[0]
        )
        self.assertTrue(created)
        self.assertEqual(template, mock_template)

        # Test retrieval of existing template
        template, created = self.vault.get_or_create_secret_template(
            "test", self.vault.owner_types[0], self.vault.secret_types[0]
        )
        self.assertFalse(created)

    def test_validate(self):
        """Test validate method."""
        template = SecretTemplate(
            name="test",
            owner_type="invalid_type",  # This should trigger validation error
            secret_type=self.vault.secret_types[0],
        )
        self.vault.secret_templates.append(template)

        with self.assertRaises(AssertionError):
            self.vault.validate()

    @patch("lx_administration.models.ansible.AnsibleInventory.from_file")
    def test_load_inventory(self, mock_from_file):
        """Test load_inventory method."""
        mock_inventory = MagicMock(spec=AnsibleInventory)
        mock_from_file.return_value = mock_inventory

        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = True
            result = self.vault.load_inventory("/fake/path")

            self.assertEqual(result, mock_inventory)
            self.assertEqual(self.vault.inventory, mock_inventory)
            mock_from_file.assert_called_once_with("/fake/path")

    @patch("lx_administration.models.vault.PreSharedKey.generate")
    def test_get_or_create_psk(self, mock_generate):
        """Test get_or_create_psk method."""
        mock_psk = PreSharedKey(
            name="test", file=str(Path(self.test_dir) / "psk" / "test.psk")
        )
        mock_generate.return_value = mock_psk

        # First call - should create new PSK
        psk, created = self.vault.get_or_create_psk("test")
        self.assertTrue(created)
        self.assertEqual(psk, mock_psk)
        self.assertIn(psk, self.vault.pre_shared_keys)

        # Mock the file exists check for the second call
        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = True
            # Second call - should return existing PSK
            psk2, created = self.vault.get_or_create_psk("test")
            self.assertFalse(created)
            self.assertEqual(psk2, psk)


if __name__ == "__main__":
    unittest.main()
