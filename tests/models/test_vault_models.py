import unittest
from configparser import ConfigParser
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from lx_administration.models import Vault
from lx_administration.models.ansible import AnsibleInventory
from lx_administration.models.vault import (
    PreSharedKey,
    Secret,
    SecretTemplate,
)
import shutil


class TestVaultModel(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.test_dir = "/tmp/test_vault"
        self.test_key = "/tmp/test_vault.key"
        self.vault = Vault(dir=self.test_dir, key=self.test_key)
        Path(self.test_dir).mkdir(parents=True, exist_ok=True)
        self.ansible_cfg_path = Path(self.test_dir) / "ansible.cfg"
        self.vault.ansible_cfg_path = self.ansible_cfg_path.as_posix()
        cfg = ConfigParser()
        cfg["defaults"] = {
            "inventory": "./ansible/inventory/hosts.ini",
            "group_vars": "./ansible/inventory/group_vars",
            "host_vars": "./ansible/inventory/host_vars",
            "roles_path": "./ansible/roles",
            "log_path": "./logs/ansible.log",
            "library": "./ansible/modules",
            "vault_identity_list": "",
            "private_key_file": "~/.ssh/id_ed25519",
        }
        cfg["privilege_escalation"] = {
            "become": "True",
            "become_method": "sudo",
            "become_user": "admin",
            "become_ask_pass": "False",
        }
        with self.ansible_cfg_path.open("w", encoding="utf-8") as fh:
            cfg.write(fh)

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
        logger = MagicMock()
        psk, created = self.vault.get_or_create_psk("test-host", logger=logger)
        self.assertTrue(created)
        self.assertEqual(psk.name, "test-host")
        self.assertIn(psk, self.vault.pre_shared_keys)

        # Test retrieving existing PSK
        psk2, created = self.vault.get_or_create_psk("test-host", logger=logger)
        self.assertFalse(created)
        self.assertEqual(psk2, psk)
        self.assertNotIn("PSK:", " ".join(str(call) for call in logger.mock_calls))

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
            value="TOP_SECRET_ROLE",
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
            value="TOP_SECRET_LOCAL",
        )

        self.vault.secret_templates.extend([role_template, local_template])
        self.vault.secrets.extend([role_secret, local_secret])

        # Test getting host secrets
        logger = MagicMock()
        host_secrets = self.vault.get_host_secrets("test-host", logger=logger)
        self.assertEqual(len(host_secrets), 2)
        self.assertIn(role_secret, host_secrets)
        self.assertIn(local_secret, host_secrets)
        log_calls = " ".join(str(call) for call in logger.mock_calls)
        self.assertNotIn("TOP_SECRET_ROLE", log_calls)
        self.assertNotIn("TOP_SECRET_LOCAL", log_calls)

    @patch("lx_administration.models.vault.manager.get_logger")
    def test_load_dir(self, mock_get_logger):
        """Load real YAML without writing vault values to logs."""
        mock_vault_data = {
            "secrets": [],
            "secret_templates": [],
            "pre_shared_keys": [],
            "dir": self.test_dir,
            "key": self.test_key,
            "owner_types": ["local", "roles", "services", "luxnix", "clients"],
            "secret_types": ["password", "key", "certificate"],
            "default_system_users": ["admin"],
            "subnet": "172.16.255.",
            "private_marker": "TOP_SECRET_MARKER",
        }
        vault_file = Path(self.test_dir) / "vault.yml"
        vault_file.write_text(yaml.safe_dump(mock_vault_data), encoding="utf-8")

        vault = Vault.load_dir(self.test_dir, self.test_key)

        self.assertIsInstance(vault, Vault)
        self.assertEqual(len(vault.secrets), 0)
        self.assertEqual(vault.dir, self.test_dir)
        self.assertEqual(vault.key, self.test_key)
        log_calls = " ".join(
            str(call) for call in mock_get_logger.return_value.mock_calls
        )
        self.assertNotIn("TOP_SECRET_MARKER", log_calls)
        mock_get_logger.return_value.info.assert_called_once_with(
            "Loaded vault metadata: secrets=%d, templates=%d, pre_shared_keys=%d",
            0,
            0,
            0,
        )

    def test_load_dir_rejects_duplicate_keys_with_path(self):
        vault_file = Path(self.test_dir) / "vault.yml"
        vault_file.write_text("secrets: []\nsecrets: []\n", encoding="utf-8")

        with self.assertRaisesRegex(yaml.YAMLError, "duplicate key 'secrets'") as error:
            Vault.load_dir(self.test_dir, self.test_key)

        self.assertIn(str(vault_file), str(error.exception))

    def test_load_dir_rejects_non_mapping_yaml(self):
        vault_file = Path(self.test_dir) / "vault.yml"
        vault_file.write_text("- not\n- a\n- vault\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Expected a YAML mapping"):
            Vault.load_dir(self.test_dir, self.test_key)

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
            "ansible_cfg_path": self.ansible_cfg_path.as_posix(),
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
        logger = MagicMock()
        self.vault.save_to_file(logger=logger)

        # Verify dump_yaml was called correctly
        mock_dump_yaml.assert_called_once()
        logger.debug.assert_not_called()
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

        with self.assertRaises(ValueError):
            self.vault.validate_vault()

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


if __name__ == "__main__":
    unittest.main()
