import unittest
from unittest.mock import patch, MagicMock, ANY
from pathlib import Path
from lx_administration.models import Vault
from lx_administration.models.vault import (
    SecretTemplate,
    PreSharedKey,
    AccessKey,
    Secret,
)
from lx_administration.models.ansible import AnsibleInventory


class TestVaultModel(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.test_dir = "/tmp/test_vault"
        self.test_key = "/tmp/test_vault.key"
        self.vault = Vault(dir=self.test_dir, key=self.test_key)

    def tearDown(self):
        """Clean up after each test method."""
        import shutil

        # Clean up any created files/directories
        test_dir_path = Path(self.test_dir)
        if test_dir_path.exists():
            shutil.rmtree(test_dir_path, ignore_errors=True)

        test_key_path = Path(self.test_key)
        if test_key_path.exists():
            try:
                test_key_path.unlink()
            except (PermissionError, FileNotFoundError):
                pass

    def test_get_vault_paths(self):
        """Test _get_vault_paths method returns correct Path objects."""
        dir_path, key_path, vault_path = Vault._get_vault_paths(
            self.test_dir, self.test_key
        )

        self.assertIsInstance(dir_path, Path)
        self.assertIsInstance(key_path, Path)
        self.assertIsInstance(vault_path, Path)
        self.assertEqual(vault_path, Path(self.test_dir) / "vault.yml")

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
        # Use the initialized self.vault from setUp
        summary = self.vault.summary()
        self.assertIsInstance(summary, str)
        self.assertIn("Vault Summary:", summary)
        self.assertIn("Secrets: 0", summary)
        self.assertIn("Access Keys: 0", summary)
        self.assertIn("Secret Templates: 0", summary)
        self.assertIn("Pre-Shared Keys: 0", summary)

    @patch("lx_administration.models.vault.manager.dump_yaml")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.mkdir")
    def test_save_to_file(self, mock_mkdir, mock_exists, mock_dump_yaml):
        """Test save_to_file method."""
        mock_exists.return_value = False

        # Create expected data structure that matches the actual Vault model
        expected_data = {
            "secrets": [],
            "access_keys": [],
            "dir": self.test_dir,
            "key": self.test_key,
            "owner_types": self.vault.owner_types,
            "secret_types": self.vault.secret_types,
            "default_client_secret_types": self.vault.default_client_secret_types,
            "default_local_secret_types": self.vault.default_local_secret_types,
            "default_system_users": self.vault.default_system_users,
            "subnet": self.vault.subnet,
            "secret_templates": [],
            "pre_shared_keys": [],
        }

        self.vault.save_to_file()

        # Verify both mkdir calls with their respective arguments
        self.assertEqual(mock_mkdir.call_count, 2)
        mock_mkdir.assert_has_calls(
            [unittest.mock.call(parents=True), unittest.mock.call(exist_ok=True)],
            any_order=True,
        )

        # Update assertion to use the actual function references
        from lx_administration.yaml import format_yaml, ansible_lint

        mock_dump_yaml.assert_called_once_with(
            expected_data, Path(self.test_dir) / "vault.yml", format_yaml, ansible_lint
        )

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

        # Test creation of new PSK
        psk, created = self.vault.get_or_create_psk("test")
        self.assertTrue(created)
        self.assertEqual(psk, mock_psk)
        self.assertIn(psk, self.vault.pre_shared_keys)

        # Test retrieval of existing PSK
        psk, created = self.vault.get_or_create_psk("test")
        self.assertFalse(created)

    def test_get_access_key(self):
        """Test get_access_key method."""
        key = AccessKey(
            name="test",
            owner_type=self.vault.owner_types[0],
            secret_type=self.vault.secret_types[0],
            file=str(Path(self.test_dir) / "keys" / "test.key"),
            vault_dir=self.test_dir,  # Add the required vault_dir parameter
        )
        self.vault.access_keys.append(key)

        result = self.vault.get_access_key("test", self.vault.owner_types[0])
        self.assertEqual(result, key)

        result = self.vault.get_access_key("nonexistent", self.vault.owner_types[0])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
