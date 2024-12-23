import os
import yaml
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from lx_admin.managers.key_file_manager import KeyFileManager

class SopsSecretManager:
    """
    A simplified SopsSecretManager that:
      - Uses absolute paths for encryption/decryption (avoiding path confusion).
      - Ensures root@root's public key is in all rules, letting 'root@root' decrypt everything.
      - Expects 'root@root' private key to be discoverable by Sops (via SOPS_AGE_KEY_FILE or default).
    """

    def __init__(
        self,
        lx_dir: str = "..",
        sops_file_path: str = "../.sops.yaml",
        key_file_path: str = "data/luxnix-identities.yaml",
        backup_user: str = "backup",
        backup_role_host: str = "root@root"
    ):
        """
        Args:
            lx_dir (str): Relative path to the top-level directory for your Nix environment.
            sops_file_path (str): Path to the "latest" .sops.yaml file.
            key_file_path (str): Path to the user identity YAML (managed by KeyFileManager).
            backup_user (str): Name of the user designated for backup (default "backup").
            backup_role_host (str): The role@host for the backup identity (default "root@root").
        """
        self.lx_dir = lx_dir
        self.sops_file_path = sops_file_path
        self.key_file_manager = KeyFileManager(key_file_path)
        self.backup_user = backup_user
        self.backup_role_host = backup_role_host

        # Load or create the sops_data structure
        if os.path.exists(self.sops_file_path):
            self._load_sops_file()
        else:
            self.sops_data = {}

        # Ensure the backup user/role and sops_age key exist
        self._ensure_backup_key_exists()

        # Insert root@root pubkey into all existing rules
        self._add_root_pubkey_to_all_rules()

    # -------------------------------------------------------------------------
    # 1) Basic Identity & Rule Management
    # -------------------------------------------------------------------------

    def list_available_identities(self) -> List[str]:
        """
        Return a list of all roles across all users in KeyFileManager.
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
        1. Ensure KeyFileManager has user_name + role_host + sops_age key.
        2. Generate default home & system rules for that role_host.
        3. Optionally add a custom named rule if create_rule_name/glob are given.
        4. Save .sops.yaml
        """
        self._ensure_user_and_role(user_name, role_host, force_new_key)

        # Figure out host portion
        if "@" in role_host:
            host_part = role_host.split("@", 1)[1]  # everything after first '@'
        else:
            host_part = role_host

        # Default "home" rule => {lx_dir}/homes/x86_64-linux/{role_host}/secrets/**
        home_rule_name = f"home-rule-{role_host}"
        home_rule_glob = f"{self.lx_dir}/homes/x86_64-linux/{role_host}/secrets/**"

        # Default "system" rule => {lx_dir}/systems/x86_64-linux/{host_part}/secrets/**
        system_rule_name = f"system-rule-{host_part}"
        system_rule_glob = f"{self.lx_dir}/systems/x86_64-linux/{host_part}/secrets/**"

        # The user/role's sops-age public key
        pub_key = self._get_sops_age_public_key(user_name, role_host)

        # Add or update default home rule
        self.add_rule(home_rule_name, home_rule_glob, [pub_key])
        # Add or update default system rule
        self.add_rule(system_rule_name, system_rule_glob, [pub_key])

        # Optionally add a custom rule
        if create_rule_name and create_rule_glob:
            self.add_rule(create_rule_name, create_rule_glob, [pub_key])

        # Save the new/updated .sops.yaml
        self.save_sops_file()

    def add_rule(
        self,
        rule_name: str,
        path_glob: str,
        sops_age_public_keys: List[str]
    ) -> None:
        """
        Create/update a named rule, merging in root@root's key as well.
        """
        creation_rules = self.sops_data.setdefault("creation_rules", [])
        root_pubkey = self._get_root_pubkey()

        # Combine user-supplied keys with the root@root key
        merged_keys = set(sops_age_public_keys)
        merged_keys.add(root_pubkey)

        for rule in creation_rules:
            if rule.get("name") == rule_name:
                rule["path_glob"] = path_glob
                existing_keys = set(rule.get("keys", []))
                rule["keys"] = list(existing_keys.union(merged_keys))
                return

        creation_rules.append({
            "name": rule_name,
            "path_glob": path_glob,
            "keys": list(merged_keys)
        })

    # -------------------------------------------------------------------------
    # 2) Create Secrets (Encryption)
    # -------------------------------------------------------------------------

    def create_secret(
        self,
        system_or_home: str,
        user_or_host: str,
        hidden: bool,
        source_file: str
    ) -> str:
        """
        Creates an encrypted secret in:
            {lx_dir}/homes/x86_64-linux/{user@host}/secrets/{general|hidden}
        or
            {lx_dir}/systems/x86_64-linux/{host}/secrets/{general|hidden}
        """
        if system_or_home == "home":
            if "@" not in user_or_host:
                raise ValueError("For 'home', user_or_host must be 'user@host'.")
            base_path = f"{self.lx_dir}/homes/x86_64-linux/{user_or_host}"
        elif system_or_home == "system":
            base_path = f"{self.lx_dir}/systems/x86_64-linux/{user_or_host}"
        else:
            raise ValueError("system_or_home must be 'system' or 'home'.")

        # Decide "secrets/general" vs "secrets/hidden"
        secrets_dir = "secrets/hidden" if hidden else "secrets/general"
        target_dir = os.path.join(base_path, secrets_dir)
        os.makedirs(target_dir, exist_ok=True)

        # Build final encrypted file path
        secret_filename = os.path.basename(source_file)
        encrypted_path = os.path.join(target_dir, secret_filename)
        if not encrypted_path.endswith(".enc"):
            encrypted_path += ".enc"

        self.encrypt_file(source_file, encrypted_path)
        print(f"[INFO] Created and encrypted secret => {encrypted_path}")
        return encrypted_path

    def encrypt_file(self, plaintext_path: str, encrypted_path: str):
        """
        Encrypt using Sops in the same directory as .sops.yaml, ensuring it
        picks up the correct config. We use absolute paths to avoid shell confusion.
        """
        # Convert to absolute paths
        in_abs = str(Path(plaintext_path).resolve())
        out_abs = str(Path(encrypted_path).resolve())

        # We'll run sops from the directory containing .sops.yaml
        sops_dir = str(Path(self.sops_file_path).resolve().parent)
        cmd = f"sops --encrypt \"{in_abs}\" > \"{out_abs}\""

        env = os.environ.copy()
        env["SOPS_CONFIG"] = str(Path(self.sops_file_path).resolve())

        result = subprocess.run(cmd, shell=True, cwd=sops_dir, env=env)
        if result.returncode != 0:
            raise RuntimeError(f"sops encryption failed with exit code {result.returncode}")

    # -------------------------------------------------------------------------
    # 3) Decryption & Re-encryption
    # -------------------------------------------------------------------------

    def decrypt_file(self, encrypted_path: str, plaintext_path: str):
        """
        Decrypt using sops, again referencing .sops.yaml in the correct dir.
        """
        in_abs = str(Path(encrypted_path).resolve())
        out_abs = str(Path(plaintext_path).resolve())

        sops_dir = str(Path(self.sops_file_path).resolve().parent)
        cmd = f"sops --decrypt \"{in_abs}\" > \"{out_abs}\""

        env = os.environ.copy()
        env["SOPS_CONFIG"] = str(Path(self.sops_file_path).resolve())

        result = subprocess.run(cmd, shell=True, cwd=sops_dir, env=env)
        if result.returncode != 0:
            raise RuntimeError(f"sops decryption failed with code {result.returncode}")

    def reencrypt_files_for_rule(self, rule_glob: str, secrets_dir: str) -> None:
        """
        Re-encrypt all secrets in secrets_dir that match rule_glob (naive approach).
        """
        path_obj = Path(secrets_dir)
        if not path_obj.exists():
            print(f"[WARN] Directory '{secrets_dir}' does not exist. Skipping re-encryption.")
            return

        for file_path in path_obj.rglob('*'):
            if file_path.is_file() and file_path.match(rule_glob):
                self._reencrypt_file(str(file_path))

    def _reencrypt_file(self, file_path: str):
        """
        Decrypt, then re-encrypt with updated rules.
        """
        tmp_path = file_path + ".decrypted"
        self.decrypt_file(file_path, tmp_path)
        self.encrypt_file(tmp_path, file_path)
        os.remove(tmp_path)

    # -------------------------------------------------------------------------
    # 4) Load / Save .sops.yaml
    # -------------------------------------------------------------------------

    def _load_sops_file(self) -> None:
        with open(self.sops_file_path, "r", encoding="utf-8") as f:
            self.sops_data = yaml.safe_load(f) or {}

    def save_sops_file(self) -> None:
        # Archive
        arch_dir = Path("data/sopsfile-archive")
        arch_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        archive_file = arch_dir / f"{ts}.sops.yaml"

        with open(archive_file, "w", encoding="utf-8") as f:
            yaml.dump(self.sops_data, f, default_flow_style=False)
        print(f"[INFO] Archived => {archive_file}")

        # Overwrite .sops.yaml
        Path(self.sops_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.sops_file_path, "w", encoding="utf-8") as f:
            yaml.dump(self.sops_data, f, default_flow_style=False)
        print(f"[INFO] Overwrote => {self.sops_file_path}")

    # -------------------------------------------------------------------------
    # 5) Backup Key & Utility
    # -------------------------------------------------------------------------

    def _ensure_backup_key_exists(self) -> None:
        """
        Ensure the backup user/role exist, plus a sops_age key. 
        """
        try:
            self.key_file_manager._get_user(self.backup_user)
        except ValueError:
            self.key_file_manager.add_user(self.backup_user)

        user_data = self.key_file_manager._get_user(self.backup_user)
        if self.backup_role_host not in user_data["roles"]:
            self.key_file_manager.add_user_role(self.backup_user, self.backup_role_host)

        has_key = "sops_age_private_key" in user_data["keys"].get(self.backup_role_host, {})
        if not has_key:
            self.key_file_manager.auto_add_key(self.backup_user, self.backup_role_host, "sops_age")

    def _add_root_pubkey_to_all_rules(self) -> None:
        """
        Insert root@root's public key into every existing rule, ensuring 
        that root@root can decrypt all secrets.
        """
        if "creation_rules" not in self.sops_data:
            return
        root_pub = self._get_root_pubkey()
        for rule in self.sops_data["creation_rules"]:
            keys = set(rule.get("keys", []))
            keys.add(root_pub)
            rule["keys"] = list(keys)

    def _get_root_pubkey(self) -> str:
        """
        Return the root@root public key from KeyFileManager.
        """
        backup_data = self.key_file_manager._get_user(self.backup_user)
        role_keys = backup_data["keys"].get(self.backup_role_host, {})
        return role_keys.get("sops_age_public_key", "")

    def _get_sops_age_public_key(self, user_name: str, role_host: str) -> str:
        """
        Return the sops_age public key from KeyFileManager for a specific user/role.
        """
        user_data = self.key_file_manager._get_user(user_name)
        return user_data["keys"][role_host]["sops_age_public_key"]

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _ensure_user_and_role(self, user_name: str, role_host: str, force_new_key: bool) -> None:
        """
        Ensure user_name / role_host exist in KeyFileManager, plus sops_age key if needed.
        """
        try:
            self.key_file_manager._get_user(user_name)
        except ValueError:
            self.key_file_manager.add_user(user_name)

        user_data = self.key_file_manager._get_user(user_name)
        if role_host not in user_data["roles"]:
            self.key_file_manager.add_user_role(user_name, role_host)

        has_sops_key = ("sops_age_private_key" in user_data["keys"].get(role_host, {}))
        if not has_sops_key or force_new_key:
            if has_sops_key:
                self.key_file_manager.auto_update_key(user_name, role_host, "sops_age")
            else:
                self.key_file_manager.auto_add_key(user_name, role_host, "sops_age")
