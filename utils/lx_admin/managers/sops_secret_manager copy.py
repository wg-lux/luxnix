"""
sops_secret_manager.py

A class that manages a "latest" .sops.yaml file (by default ../.sops.yaml),
automatically creating a time-stamped backup in data/sopsfile-archive/{timestamp}.sops.yaml
before overwriting the "latest" file.

Improvements:
- Each rule now has a "name" field for easier referencing.
- Methods to list all rules with their order, move a rule's position, 
  and update existing rules by index.
"""

import os
import yaml
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from cryptography.hazmat.backends import default_backend
from lx_admin.managers.key_file_manager import KeyFileManager


class SopsSecretManager:
    """
    A class that manages a .sops.yaml file, secret encryption/decryption using sops,
    and integration with KeyFileManager for user/identity handling.

    On each save:
      1) Create a time-stamped archive copy in data/sopsfile-archive/{timestamp}.sops.yaml
      2) Overwrite ../.sops.yaml (or whatever self.sops_file_path is) with the same data.

    Each 'creation_rules' entry has the following structure:
        {
          "name": "<RULE_NAME>",
          "path_glob": "./some/pattern/*",
          "keys": [
            "age1xxxxxx...",
            "age1yyyyyy...",
            ...
          ]
        }

    The "keys" array is always merged with the designated backup key.
    """

    def __init__(
        self,
        sops_file_path: str = "../.sops.yaml",
        key_file_path: str = "data/luxnix-identities.yaml",
        backup_user: str = "backup",
        backup_role_host: str = "root@root"
    ):
        """
        Args:
            sops_file_path (str): Path to the "latest" .sops.yaml file (default ../.sops.yaml).
            key_file_path (str): Path to the user identity YAML (managed by KeyFileManager).
            backup_user (str): Name of the user designated for backup (default "backup").
            backup_role_host (str): Role@host for the backup identity (default "root@root").
        """
        self.sops_file_path = sops_file_path
        self.key_file_manager = KeyFileManager(key_file_path)
        self.backup_user = backup_user
        self.backup_role_host = backup_role_host

        # Load or create the .sops.yaml data
        if os.path.exists(sops_file_path):
            self._load_sops_file()
        else:
            self.sops_data = {}

        # Ensure our designated backup user and role exist with a sops_age key
        self._ensure_backup_key_exists()

    # -------------------------------------------------------------------------
    # Higher-Level Identity & Key Management
    # -------------------------------------------------------------------------

    def list_available_identities(self) -> List[str]:
        """
        Retrieve a list of all roles (e.g. 'admin@hostname') across all users
        from the KeyFileManager.
        """
        all_identities = []
        for user in self.key_file_manager.get_users_data():
            all_identities.extend(user["roles"])
        return all_identities

    def add_or_update_user_identity(
        self,
        user_name: str,
        role_host: str,
        create_rule_name: Optional[str] = None,
        create_rule_glob: Optional[str] = None,
        force_new_key: bool = False
    ) -> None:
        """
        Add or update a user/role in the identity YAML and optionally add a 
        named creation rule in .sops.yaml for the secrets that this identity can access.

        If both create_rule_name and create_rule_glob are provided, a new rule 
        (or updated rule) will be added with that name, path_glob, and the user's sops_age key.
        """
        # 1. Ensure user
        try:
            self.key_file_manager._get_user(user_name)
        except ValueError:
            self.key_file_manager.add_user(user_name)

        user = self.key_file_manager._get_user(user_name)

        # 2. Ensure role
        if role_host not in user["roles"]:
            self.key_file_manager.add_user_role(user_name, role_host)

        # 3. Ensure sops_age key
        has_sops_key = "sops_age_private_key" in user["keys"].get(role_host, {})
        if not has_sops_key or force_new_key:
            if has_sops_key:
                self.key_file_manager.auto_update_key(user_name, role_host, "sops_age")
            else:
                self.key_file_manager.auto_add_key(user_name, role_host, "sops_age")

        # 4. If needed, add or update a named creation rule
        if create_rule_name and create_rule_glob:
            pub_key = self._get_sops_age_public_key(user_name, role_host)
            self.add_rule(
                rule_name=create_rule_name,
                path_glob=create_rule_glob,
                sops_age_public_keys=[pub_key]
            )
            self.save_sops_file()

    def reencrypt_files_for_rule(
        self,
        rule_glob: str,
        secrets_dir: str = "data/sops-secrets"
    ) -> None:
        """
        Re-encrypt all secrets matching the given `rule_glob` to ensure
        new or updated keys take effect.

        This example still uses a naive approach by enumerating all files
        in `secrets_dir`. If you only want to re-encrypt certain files, 
        refine the logic below.
        """
        base_path = Path(secrets_dir)
        if not base_path.exists():
            print(f"No directory '{secrets_dir}' found. Skipping re-encryption.")
            return

        for file_path in base_path.rglob('*'):
            if file_path.is_file():
                self._reencrypt_file(str(file_path))

    # -------------------------------------------------------------------------
    # Named Rule Management
    # -------------------------------------------------------------------------

    def add_rule(
        self,
        rule_name: str,
        path_glob: str,
        sops_age_public_keys: List[str]
    ) -> None:
        """
        Add a new named rule. If a rule with this name already exists, we update it
        (preserving its position in the creation_rules list).

        The 'keys' array is merged with the backup key. If the rule doesn't exist, 
        we append it to the end of creation_rules.
        """
        creation_rules = self.sops_data.setdefault("creation_rules", [])

        backup_pubkey = self._get_backup_public_key()
        merged_keys = set(sops_age_public_keys)
        merged_keys.add(backup_pubkey)

        # Try to find an existing rule with the same name
        for rule in creation_rules:
            if rule.get("name") == rule_name:
                # Update the rule
                rule["path_glob"] = path_glob
                existing_keys = set(rule.get("keys", []))
                rule["keys"] = list(existing_keys.union(merged_keys))
                return

        # Otherwise, create a new rule at the end
        new_rule = {
            "name": rule_name,
            "path_glob": path_glob,
            "keys": list(merged_keys)
        }
        creation_rules.append(new_rule)

    def update_rule(
        self,
        rule_index: int,
        new_name: Optional[str] = None,
        new_path_glob: Optional[str] = None,
        new_keys: Optional[List[str]] = None
    ) -> None:
        """
        Update the name, path_glob, or keys of an existing rule by index.
        If new_keys are specified, we also merge them with the backup key.

        Raises:
            IndexError: If the rule_index is invalid.
        """
        creation_rules = self.sops_data.get("creation_rules", [])
        if rule_index < 0 or rule_index >= len(creation_rules):
            raise IndexError(f"Invalid rule index: {rule_index}.")

        rule = creation_rules[rule_index]

        if new_name is not None:
            rule["name"] = new_name
        if new_path_glob is not None:
            rule["path_glob"] = new_path_glob
        if new_keys is not None:
            backup_pubkey = self._get_backup_public_key()
            merged_keys = set(new_keys)
            merged_keys.add(backup_pubkey)
            rule["keys"] = list(merged_keys)

    def list_rules(self) -> List[Dict]:
        """
        Return the list of rules, preserving their order.

        Each item is a dict:
            {
              "name": ...,
              "path_glob": ...,
              "keys": [...]
            }

        You can print or iterate over the returned list.
        """
        return self.sops_data.get("creation_rules", [])

    def move_rule(self, old_index: int, new_index: int) -> None:
        """
        Move a rule from old_index to new_index in the creation_rules list.

        This allows you to reorder rules easily.

        Raises:
            IndexError: If old_index or new_index is out of range.
        """
        creation_rules = self.sops_data.get("creation_rules", [])
        if old_index < 0 or old_index >= len(creation_rules):
            raise IndexError(f"old_index is out of range: {old_index}")
        if new_index < 0 or new_index >= len(creation_rules):
            raise IndexError(f"new_index is out of range: {new_index}")
        rule = creation_rules.pop(old_index)
        creation_rules.insert(new_index, rule)

    # -------------------------------------------------------------------------
    # Internal: Loading, Saving & Archiving
    # -------------------------------------------------------------------------

    def _load_sops_file(self) -> None:
        """Load the existing .sops.yaml file content into memory."""
        with open(self.sops_file_path, 'r', encoding="utf-8") as f:
            self.sops_data = yaml.safe_load(f) or {}

    def save_sops_file(self) -> None:
        """
        1) Create an archive version in data/sopsfile-archive/{timestamp}.sops.yaml
        2) Overwrite the "latest" file (self.sops_file_path) with the same data
        """
        archive_dir = Path("data/sopsfile-archive")
        archive_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        archive_file = archive_dir / f"{timestamp}.sops.yaml"

        # 1) Archive
        with open(archive_file, "w", encoding="utf-8") as f:
            yaml.dump(self.sops_data, f, default_flow_style=False)
        print(f"Archived .sops.yaml => {archive_file}")

        # 2) Overwrite 'latest'
        os.makedirs(os.path.dirname(self.sops_file_path), exist_ok=True)
        with open(self.sops_file_path, "w", encoding="utf-8") as f:
            yaml.dump(self.sops_data, f, default_flow_style=False)
        print(f"Overwrote 'latest' => {self.sops_file_path}")

    # -------------------------------------------------------------------------
    # Encryption / Decryption Helpers
    # -------------------------------------------------------------------------

    def _reencrypt_file(self, file_path: str) -> None:
        """
        Decrypt, then re-encrypt a file with the updated rules.
        """
        tmp_path = file_path + ".decrypted"
        os.system(f"sops --decrypt {file_path} > {tmp_path}")
        os.system(f"sops --encrypt {tmp_path} > {file_path}")
        os.remove(tmp_path)

    def encrypt_file(self, plaintext_path: str, encrypted_path: str):
        os.makedirs(os.path.dirname(encrypted_path), exist_ok=True)
        os.system(f"sops --encrypt {plaintext_path} > {encrypted_path}")

    def decrypt_file(self, encrypted_path: str, plaintext_path: str):
        os.makedirs(os.path.dirname(plaintext_path), exist_ok=True)
        os.system(f"sops --decrypt {encrypted_path} > {plaintext_path}")

    # -------------------------------------------------------------------------
    # Backup Key / Utility
    # -------------------------------------------------------------------------

    def _ensure_backup_key_exists(self) -> None:
        """
        Ensure the backup user/role have a sops_age key.
        """
        try:
            self.key_file_manager._get_user(self.backup_user)
        except ValueError:
            self.key_file_manager.add_user(self.backup_user)

        user_data = self.key_file_manager._get_user(self.backup_user)
        if self.backup_role_host not in user_data["roles"]:
            self.key_file_manager.add_user_role(self.backup_user, self.backup_role_host)

        has_sops_key = "sops_age_private_key" in user_data["keys"].get(self.backup_role_host, {})
        if not has_sops_key:
            self.key_file_manager.auto_add_key(self.backup_user, self.backup_role_host, "sops_age")

    def _get_backup_public_key(self) -> str:
        """
        Retrieve the backup user's sops_age public key from KeyFileManager.
        """
        backup_data = self.key_file_manager._get_user(self.backup_user)
        return backup_data["keys"][self.backup_role_host]["sops_age_public_key"]

    def _get_sops_age_public_key(self, user_name: str, role_host: str) -> str:
        """
        Retrieve the given user's sops_age public key from KeyFileManager.
        """
        user_data = self.key_file_manager._get_user(user_name)
        return user_data["keys"][role_host]["sops_age_public_key"]
