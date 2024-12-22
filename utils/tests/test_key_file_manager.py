import unittest
import tempfile
import os
import yaml
from pathlib import Path

# Adjust import paths if needed
from lx_admin.managers.key_file_manager import KeyFileManager


class TestKeyFileManager(unittest.TestCase):
    def setUp(self):
        """
        Create a temporary YAML file with dummy data before each test.
        """
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_yaml_path = os.path.join(self.tmp_dir.name, "test_identities.yaml")

        # Example initial YAML content
        self.initial_data = {
            "users": [
                {
                    "name": "alice",
                    "roles": ["admin@host1"],
                    "keys": {
                        "admin@host1": {
                            "rsa_private_key": "fake_rsa_priv",
                            "rsa_public_key": "fake_rsa_pub",
                            "created": "2024-01-01T00:00:00",
                            "updated": "2024-01-01T00:00:00"
                        }
                    }
                }
            ]
        }

        with open(self.test_yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(self.initial_data, f)

    def tearDown(self):
        """
        Remove temporary files/folders after each test.
        """
        self.tmp_dir.cleanup()

    def test_init_and_load(self):
        """
        Test that KeyFileManager loads the YAML file properly.
        """
        manager = KeyFileManager(self.test_yaml_path)
        data = manager.get_users_data()
        self.assertEqual(len(data), 1, "Should load 1 user from the file.")
        self.assertEqual(data[0]["name"], "alice", "User name should be 'alice'")

    def test_add_user(self):
        """
        Test adding a new user.
        """
        manager = KeyFileManager(self.test_yaml_path)
        manager.add_user("bob")
        data = manager.get_users_data()
        self.assertEqual(len(data), 2, "Should have 2 users now.")
        self.assertIn("bob", [user["name"] for user in data], "New user 'bob' missing.")

    def test_remove_user(self):
        """
        Test removing an existing user.
        """
        manager = KeyFileManager(self.test_yaml_path)
        manager.remove_user("alice")
        data = manager.get_users_data()
        self.assertEqual(len(data), 0, "All users should have been removed.")

    def test_add_user_role(self):
        """
        Test adding a new role to an existing user.
        """
        manager = KeyFileManager(self.test_yaml_path)
        manager.add_user_role("alice", "developer@host2")
        data = manager.get_users_data()
        alice = next(u for u in data if u["name"] == "alice")
        self.assertIn("developer@host2", alice["roles"], "Role was not added.")

    def test_remove_user_role(self):
        """
        Test removing a role from an existing user.
        """
        manager = KeyFileManager(self.test_yaml_path)
        manager.remove_user_role("alice", "admin@host1")
        data = manager.get_users_data()
        alice = next(u for u in data if u["name"] == "alice")
        self.assertNotIn("admin@host1", alice["roles"], "Role was not removed.")

    def test_add_user_key(self):
        """
        Test adding a new key to an existing user and role.
        """
        manager = KeyFileManager(self.test_yaml_path)
        manager.add_user_role("alice", "dev@host2")
        manager.add_user_key("alice", "dev@host2", "rsa", "rsa_priv", "rsa_pub")

        data = manager.get_users_data()
        alice_keys = next(u for u in data if u["name"] == "alice")["keys"]
        self.assertIn("dev@host2", alice_keys, "Key entry for dev@host2 not found.")
        self.assertIn("rsa_private_key", alice_keys["dev@host2"], "No RSA private key.")
        self.assertIn("rsa_public_key", alice_keys["dev@host2"], "No RSA public key.")

    def test_process_users_script_integration(self):
        """
        (Optional) Test an end-to-end integration, 
        ensuring the user_keygen.process_users function works.
        
        This assumes your user_keygen module has a `process_users` function 
        that populates new keys for each user and role.
        """
        try:
            from user_keygen import process_users
        except ImportError:
            self.skipTest("user_keygen not found or process_users not implemented")

        output_yaml_path = os.path.join(self.tmp_dir.name, "output_identities.yaml")

        # Run process_users (it should add keys for all existing roles)
        process_users(self.test_yaml_path, output_yaml_path)

        # Check that the output file has expanded keys for alice's admin@host1
        with open(output_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        alice_entry = data["users"][0]
        self.assertIn("admin@host1", alice_entry["keys"], "No keys found for admin@host1")
        self.assertIn("rsa_private_key", alice_entry["keys"]["admin@host1"], "Missing RSA private key after process_users")

        # Further checks can be made for Ed25519, sops_age, etc.


if __name__ == "__main__":
    unittest.main()
