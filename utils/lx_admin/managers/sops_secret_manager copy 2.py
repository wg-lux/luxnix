"""
sops_secret_manager.py

Extended to automatically create two default rules for each identity:
  1) {lxDir}/homes/x86_64-linux/{user@host}/secrets/*
  2) {lxDir}/systems/x86_64-linux/{host}/secrets/*

The constructor receives `lx_dir` so we know the base path.
"""

import os
import yaml
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from lx_admin.managers.key_file_manager import KeyFileManager


class SopsSecretManager:
    def __init__(
        self,
        lx_dir: str,
        sops_file_path: str = "../.sops.yaml",
        key_file_path: str = "data/luxnix-identities.yaml",
        backup_user: str = "backup",
        backup_role_host: str = "root@root"
    ):
        """
        Args:
            lx_dir (str): The top-level directory for your Nix environment (e.g. ".." if we run from {lxDir}/utils).
            sops_file_path (str): Path to the "latest" .sops.yaml file (default ../.sops.yaml).
            key_file_path (str): Path to the user identity YAML (managed by KeyFileManager).
            backup_user (str): Name of the user designated for backup (default "backup").
            backup_role_host (str): Role@host for the backup identity (default "root@root").
        """
        self.lx_dir = lx_dir
        self.sops_file_path = sops_file_path
        self.key_file_manager = KeyFileManager(key_file_path)
        self.backup_user = backup_user
        self.backup_role_host = backup_role_host

        if os.path.exists(self.sops_file_path):
            self._load_sops_file()
        else:
            self.sops_data = {}

        self._ensure_backup_key_exists()

    def list_available_identities(self) -> List[str]:
        """
        Retrieve a list of all roles (e.g. 'admin@hostname') across all users
        from the KeyFileManager.
        """
        all_identities = []
        for user in self.key_file_manager.get_users_data():
            all_identities.extend(user["roles"])
        return all_identities

    # -------------------------------------------------------------------------
    # Identity Management & Default Rules
    # -------------------------------------------------------------------------

    def add_or_update_user_identity(
        self,
        user_name: str,          # e.g. "alice"
        role_host: str,          # e.g. "alice@myhost"
        create_rule_name: Optional[str] = None,  # If you want a special named rule
        create_rule_glob: Optional[str] = None,
        force_new_key: bool = False
    ) -> None:
        """
        Add or update a user/role in the identity YAML (KeyFileManager).
        Then automatically create default system/home rules for this role_host,
        plus optionally create a custom named rule if specified.
        """
        # 1. Ensure the user/role in KeyFileManager
        self._ensure_user_and_role(user_name, role_host, force_new_key=force_new_key)

        # 2. Add default rules (home and system) for this role_host
        #    user@host => "host" is the substring after "@"
        if "@" in role_host:
            host_part = role_host.split("@")[-1]
            user_part = role_host.split("@")[0]
        else:
            # fallback, or raise an error if you expect always user@host
            host_part = role_host
            user_part = role_host  # or some fallback

        # Default home rule
        home_rule_name = f"home-rule-{role_host}"
        home_rule_glob = f"{self.lx_dir}/homes/x86_64-linux/{role_host}/secrets/**"
        # Default system rule
        system_rule_name = f"system-rule-{host_part}"
        system_rule_glob = f"{self.lx_dir}/systems/x86_64-linux/{host_part}/secrets/**"

        # we fetch the sops_age pub key for the role
        pub_key = self._get_sops_age_public_key(user_name, role_host)

        # create / update the home rule
        self.add_rule(
            rule_name=home_rule_name,
            path_glob=home_rule_glob,
            sops_age_public_keys=[pub_key]
        )
        # create / update the system rule
        self.add_rule(
            rule_name=system_rule_name,
            path_glob=system_rule_glob,
            sops_age_public_keys=[pub_key]
        )

        # 3. If a custom named rule is also requested
        if create_rule_name and create_rule_glob:
            self.add_rule(
                rule_name=create_rule_name,
                path_glob=create_rule_glob,
                sops_age_public_keys=[pub_key]
            )

        # 4. Finally, save the sops file
        self.save_sops_file()

    def _ensure_user_and_role(self, user_name: str, role_host: str, force_new_key: bool) -> None:
        """
        Ensure the user and role exist in KeyFileManager and that there's a sops_age key.
        """
        # Make sure the user object exists
        try:
            self.key_file_manager._get_user(user_name)
        except ValueError:
            self.key_file_manager.add_user(user_name)

        user_data = self.key_file_manager._get_user(user_name)
        # Ensure role
        if role_host not in user_data["roles"]:
            self.key_file_manager.add_user_role(user_name, role_host)

        # Ensure sops_age key
        has_sops_key = "sops_age_private_key" in user_data["keys"].get(role_host, {})
        if not has_sops_key or force_new_key:
            if has_sops_key:
                self.key_file_manager.auto_update_key(user_name, role_host, "sops_age")
            else:
                self.key_file_manager.auto_add_key(user_name, role_host, "sops_age")

    # -------------------------------------------------------------------------
    # Create a new secret for system or home
    # -------------------------------------------------------------------------

    def create_secret(
        self,
        system_or_home: str,    # "system" or "home"
        user_or_host: str,      # e.g. "alice@myhost" or just "myhost" if system
        hidden: bool,           # If true => secrets/hidden, else => secrets/general
        source_file: str        # Path to the plaintext file
    ) -> str:
        """
        Create a new secret file. The location depends on whether it's for a 'system' or 'home'.

        For 'home', we require user@host. We'll store the secret in:
            {lx_dir}/homes/x86_64-linux/{user@host}/secrets/<general|hidden>/

        For 'system', we require the host. We'll store the secret in:
            {lx_dir}/systems/x86_64-linux/{host}/secrets/<general|hidden>/

        Returns: The path to the newly created encrypted secret file.
        """
        if system_or_home not in ("system", "home"):
            raise ValueError("system_or_home must be 'system' or 'home'.")

        if system_or_home == "home":
            # Expect user@host, parse the host portion
            if "@" not in user_or_host:
                raise ValueError("For home secrets, please provide user@host, e.g. 'alice@myhost'.")
            base_path = f"{self.lx_dir}/homes/x86_64-linux/{user_or_host}"
        else:
            # system => user_or_host is actually just the hostname
            base_path = f"{self.lx_dir}/systems/x86_64-linux/{user_or_host}"

        # Decide directory: "secrets/general" or "secrets/hidden"
        secrets_subdir = "secrets/hidden" if hidden else "secrets/general"
        target_dir = os.path.join(base_path, secrets_subdir)
        os.makedirs(target_dir, exist_ok=True)

        # We name the secret file the same as the source file, or some custom logic
        secret_filename = os.path.basename(source_file)
        encrypted_path = os.path.join(target_dir, secret_filename)

        # Actually do the encryption using sops CLI
        # We assume we want an .enc extension or something; adapt as needed
        if not encrypted_path.endswith(".enc"):
            encrypted_path += ".enc"

        self.encrypt_file(source_file, encrypted_path)
        print(f"Created and encrypted secret => {encrypted_path}")

        return encrypted_path

    # -------------------------------------------------------------------------
    # Re-encrypt existing secrets
    # -------------------------------------------------------------------------
    def reencrypt_files_for_rule(self, rule_glob: str, secrets_dir: str) -> None:
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
    # Named Rule Management (unchanged from previous version)
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
    # Loading, Saving, etc.
    # -------------------------------------------------------------------------
    def _load_sops_file(self) -> None:
        with open(self.sops_file_path, 'r', encoding='utf-8') as f:
            self.sops_data = yaml.safe_load(f) or {}

    def save_sops_file(self) -> None:
        archive_dir = Path("data/sopsfile-archive")
        archive_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        archive_file = archive_dir / f"{timestamp}.sops.yaml"

        with open(archive_file, "w", encoding="utf-8") as f:
            yaml.dump(self.sops_data, f, default_flow_style=False)
        print(f"Archived => {archive_file}")

        os.makedirs(os.path.dirname(self.sops_file_path), exist_ok=True)
        with open(self.sops_file_path, "w", encoding="utf-8") as f:
            yaml.dump(self.sops_data, f, default_flow_style=False)
        print(f"Overwrote => {self.sops_file_path}")

    # -------------------------------------------------------------------------
    # Sops Encryption Helpers
    # -------------------------------------------------------------------------
    def encrypt_file(self, plaintext_path: str, encrypted_path: str):
        os.makedirs(os.path.dirname(encrypted_path), exist_ok=True)
        cmd = f"sops --encrypt {plaintext_path} > {encrypted_path}"
        os.system(cmd)

    def decrypt_file(self, encrypted_path: str, plaintext_path: str):
        os.makedirs(os.path.dirname(plaintext_path), exist_ok=True)
        os.system(f"sops --decrypt {encrypted_path} > {plaintext_path}")

    
    def _reencrypt_file(self, file_path: str):
        """
        Decrypt, then re-encrypt a file with the updated rules.
        """
        tmp_path = file_path + ".decrypted"
        os.system(f"sops --decrypt {file_path} > {tmp_path}")
        os.system(f"sops --encrypt {tmp_path} > {file_path}")
        os.remove(tmp_path)

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
