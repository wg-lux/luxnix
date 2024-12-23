"""
test_sops_secret_manager.py

Unittests for the SopsSecretManager class, verifying:
  - Integration with KeyFileManager for user/role creation and key generation
  - Named .sops.yaml creation rules (with rule name, path_glob, and keys)
  - Updating, listing, and reordering rules
  - Re-encrypting secrets (mocked sops calls)
"""

import unittest
import tempfile
import os
from unittest.mock import patch, MagicMock
import yaml

from pathlib import Path

# Adjust these imports to match your actual structure:
from lx_admin.managers.sops_secret_manager import SopsSecretManager
from lx_admin.managers.key_file_manager import KeyFileManager


class TestSopsSecretManager(unittest.TestCase):
    def setUp(self):
        """
        Create temporary directories and files, including a sample identity YAML
        and sample .sops.yaml.
        """
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.key_file_path = os.path.join(self.tmp_dir.name, "identities.yaml")
        self.sops_file_path = os.path.join(self.tmp_dir.name, "my_sops.yaml")

        # Minimal KeyFileManager structure
        initial_identities = {
            "users": [
                {
                    "name": "alice",
                    "roles": ["admin@host1"],
                    "keys": {}
                }
            ]
        }
        with open(self.key_file_path, "w", encoding="utf-8") as f:
            yaml.dump(initial_identities, f)

        # Minimal sops data
        initial_sops = {
            "creation_rules": []
        }
        with open(self.sops_file_path, "w", encoding="utf-8") as f:
            yaml.dump(initial_sops, f)

    def tearDown(self):
        self.tmp_dir.cleanup()

    # -------------------------------------------------------------------------
    # Helper to create a SopsSecretManager instance
    # -------------------------------------------------------------------------
    def _create_manager(self):
        """
        Create a SopsSecretManager with a temporary lx_dir (use self.tmp_dir.name 
        to simulate your top-level folder).
        """
        return SopsSecretManager(
            lx_dir=self.tmp_dir.name,               # or some other path if you prefer
            sops_file_path=self.sops_file_path,
            key_file_path=self.key_file_path,
            backup_user="backup",
            backup_role_host="root@root"
        )

    # -------------------------------------------------------------------------
    # Existing Tests
    # -------------------------------------------------------------------------

    def test_list_available_identities(self):
        """
        Test listing available identities from KeyFileManager.
        """
        sops_mgr = self._create_manager()
        identities = sops_mgr.list_available_identities()
        self.assertIn("admin@host1", identities, "Should list existing roles from identities.yaml")

    def test_add_or_update_user_identity_creates_user_and_role(self):
        """
        Test that if we call add_or_update_user_identity with a user and role that doesn't exist,
        it will be created in KeyFileManager, plus a new sops_age key is generated.
        """
        sops_mgr = self._create_manager()

        # Add a new user "bob" with a role "dev@host2"
        sops_mgr.add_or_update_user_identity("bob", "dev@host2")

        # Check identities
        manager = KeyFileManager(self.key_file_path)
        users_data = manager.get_users_data()
        bob_entry = next(u for u in users_data if u["name"] == "bob")
        self.assertIn("dev@host2", bob_entry["roles"], "dev@host2 role not created.")
        self.assertIn(
            "sops_age_private_key",
            bob_entry["keys"]["dev@host2"],
            "No sops_age key created for dev@host2."
        )

    def test_add_or_update_user_identity_force_new_key(self):
        """
        Verify that force_new_key replaces an existing sops_age key for that user/role.
        """
        sops_mgr = self._create_manager()

        # First call: create sops_age key
        sops_mgr.add_or_update_user_identity("alice", "admin@host1")
        manager = KeyFileManager(self.key_file_path)
        alice_data = next(u for u in manager.get_users_data() if u["name"] == "alice")
        old_private_key = alice_data["keys"]["admin@host1"]["sops_age_private_key"]

        # Second call with force_new_key = True
        sops_mgr.add_or_update_user_identity("alice", "admin@host1", force_new_key=True)
        manager = KeyFileManager(self.key_file_path)
        alice_data = next(u for u in manager.get_users_data() if u["name"] == "alice")
        new_private_key = alice_data["keys"]["admin@host1"]["sops_age_private_key"]

        self.assertNotEqual(
            old_private_key,
            new_private_key,
            "Private key should be replaced with a new one when force_new_key=True."
        )

    def test_add_or_update_user_identity_with_creation_rule(self):
        """
        If create_rule_glob is provided (and a name), we expect the new sops_age key 
        to appear in the .sops.yaml creation_rules.
        """
        sops_mgr = self._create_manager()

        # Provide BOTH a name and a glob
        rule_name = "alice-secret-rule"
        rule_glob = "./homes/x86_64-linux/admin@host2/secrets/*"
        
        sops_mgr.add_or_update_user_identity(
            user_name="alice",
            role_host="admin@host2",
            create_rule_name=rule_name,
            create_rule_glob=rule_glob
        )

        # Check .sops.yaml
        with open(self.sops_file_path, "r", encoding="utf-8") as f:
            sops_data = yaml.safe_load(f)

        self.assertGreater(
            len(sops_data["creation_rules"]), 
            0, 
            "No creation rules found in .sops.yaml after adding a rule."
        )
        last_rule = sops_data["creation_rules"][-1]
        self.assertIn("path_glob", last_rule, "Rule should have path_glob.")
        self.assertEqual(
            last_rule["path_glob"], 
            rule_glob, 
            "Rule glob mismatch."
        )
        self.assertGreater(
            len(last_rule["keys"]), 
            0, 
            "Should have at least one sops_age public key in the rule keys."
        )
        self.assertEqual(
            last_rule["name"], 
            rule_name,
            "Rule name mismatch; the new code sets a rule name."
        )

    @patch("os.system")
    def test_reencrypt_files_for_rule(self, mock_system):
        """
        Test reencrypt_files_for_rule by verifying it calls a re-encryption routine on 
        all secrets in the designated directory, and ensure the decrypted file is mocked.
        """
        def side_effect_os_system(command):
            # If the command is a 'sops --decrypt' command like:
            #   sops --decrypt /some/path > /another/path.decrypted
            # we parse out the output file and create a dummy file for it
            if "sops --decrypt" in command:
                parts = command.split(">")
                if len(parts) == 2:
                    decrypted_path = parts[1].strip()
                    with open(decrypted_path, "w") as f:
                        f.write("decrypted content")
            # Similarly for "sops --encrypt" if needed
            return 0  # success

        mock_system.side_effect = side_effect_os_system

        sops_mgr = self._create_manager()

        # Create a dummy secret file
        secrets_dir = os.path.join(self.tmp_dir.name, "sops-secrets")
        os.makedirs(secrets_dir, exist_ok=True)
        secret_file = os.path.join(secrets_dir, "mysecret.enc")
        with open(secret_file, "w") as f:
            f.write("encrypted content")

        # The re-encrypt method calls _reencrypt_file
        sops_mgr.reencrypt_files_for_rule(rule_glob="*.enc", secrets_dir=secrets_dir)

        # If no FileNotFoundError was raised, the test passes
        self.assertTrue(os.path.exists(secret_file), "Secret file should still exist after re-encrypt.")

    # -------------------------------------------------------------------------
    # New Tests for Named Rules & Reordering
    # -------------------------------------------------------------------------

    def test_add_named_rule_and_save(self):
        """
        Test creating a named rule (via add_rule) and verifying it appears in creation_rules.
        """
        sops_mgr = self._create_manager()

        # Add a named rule with a custom path_glob
        sops_mgr.add_rule(
            rule_name="dev-secrets",
            path_glob="./dev/projectA/secrets/*",
            sops_age_public_keys=["age1fakeAAAA", "age1fakeBBBB"]
        )
        sops_mgr.save_sops_file()

        # Check the .sops.yaml on disk
        with open(self.sops_file_path, "r", encoding="utf-8") as f:
            sops_data = yaml.safe_load(f)

        rules = sops_data.get("creation_rules", [])
        self.assertEqual(len(rules), 1, "Should have exactly 1 rule after adding dev-secrets.")
        self.assertEqual(rules[0]["name"], "dev-secrets", "Rule name mismatch.")
        self.assertEqual(rules[0]["path_glob"], "./dev/projectA/secrets/*", "Path glob mismatch.")
        # Should contain at least the 2 keys plus the backup key
        self.assertGreaterEqual(len(rules[0]["keys"]), 2, "Should have at least 2 keys (user + backup).")

    def test_update_rule_data(self):
        """
        Test updating an existing rule by index (name, path_glob, keys).
        """
        sops_mgr = self._create_manager()

        # Add a named rule
        sops_mgr.add_rule(
            rule_name="initial-rule",
            path_glob="./old/path/*",
            sops_age_public_keys=["age1fakeKEY1"]
        )
        sops_mgr.save_sops_file()

        # Now update the rule
        sops_mgr.update_rule(
            rule_index=0,
            new_name="updated-rule",
            new_path_glob="./new/path/*",
            new_keys=["age1fakeNEWKEY"]
        )
        sops_mgr.save_sops_file()

        with open(self.sops_file_path, "r", encoding="utf-8") as f:
            sops_data = yaml.safe_load(f)

        rule = sops_data["creation_rules"][0]
        self.assertEqual(rule["name"], "updated-rule", "Rule name was not updated.")
        self.assertEqual(rule["path_glob"], "./new/path/*", "Rule path_glob was not updated.")
        # Should have new_keys plus the backup key
        self.assertIn("age1fakeNEWKEY", rule["keys"], "Updated keys not found in rule.")
        self.assertGreaterEqual(len(rule["keys"]), 2, "Should have updated key + backup key.")

    def test_rule_order_and_move(self):
        """
        Test adding multiple rules, then reordering them with move_rule.
        """
        sops_mgr = self._create_manager()

        # Add multiple named rules
        sops_mgr.add_rule("rule-A", "./pathA/*", ["age1A"])
        sops_mgr.add_rule("rule-B", "./pathB/*", ["age1B"])
        sops_mgr.add_rule("rule-C", "./pathC/*", ["age1C"])
        sops_mgr.save_sops_file()

        # Check order
        initial_rules = sops_mgr.list_rules()
        self.assertEqual(len(initial_rules), 3, "Should have 3 rules.")
        self.assertEqual(initial_rules[0]["name"], "rule-A", "First rule mismatch.")
        self.assertEqual(initial_rules[1]["name"], "rule-B", "Second rule mismatch.")
        self.assertEqual(initial_rules[2]["name"], "rule-C", "Third rule mismatch.")

        # Move rule-B (index=1) to index=0
        sops_mgr.move_rule(old_index=1, new_index=0)
        sops_mgr.save_sops_file()

        # Check new order
        new_rules = sops_mgr.list_rules()
        self.assertEqual(new_rules[0]["name"], "rule-B", "rule-B should now be at index 0.")
        self.assertEqual(new_rules[1]["name"], "rule-A", "rule-A should move to index 1.")
        self.assertEqual(new_rules[2]["name"], "rule-C", "rule-C remains at index 2.")


if __name__ == "__main__":
    unittest.main()
