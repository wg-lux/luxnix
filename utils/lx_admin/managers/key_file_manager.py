"""
KeyFileManager class for handling users, roles, and keys in a YAML file.
"""

import os
from datetime import datetime
from pathlib import Path
import subprocess

import yaml
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ed25519

# Import your own local modules
from .ssh_key_utils import (
    handle_rsa_keys,
    handle_ed25519_keys
)
from .sops_age_utils import deploy_sops_age_keys


def generate_sops_age_key():
    """
    Generates a sops-age key pair using the `age` CLI tool.

    Returns:
        tuple: (private_key, public_key)
    """
    result = subprocess.run(["age-keygen"], capture_output=True, text=True, check=True)
    private_key = result.stdout.strip()
    public_key = next(
        line for line in private_key.splitlines() if line.startswith("# public key: ")
    ).replace("# public key: ", "")
    return private_key, public_key


def generate_key_pair(key_type="rsa"):
    """
    Generates a private and public key pair for rsa, ed25519, or sops_age.

    Args:
        key_type (str): Type of key to generate ("rsa", "ed25519", "sops_age").

    Returns:
        tuple: (private_key_pem_or_text, public_key_pem_or_text)
    """
    if key_type == "rsa":
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        public_key = private_key.public_key()
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        return private_key_pem, public_key_pem

    elif key_type == "ed25519":
        private_key = ed25519.Ed25519PrivateKey.generate()
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        public_key = private_key.public_key()
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        return private_key_pem, public_key_pem

    elif key_type == "sops_age":
        return generate_sops_age_key()

    else:
        raise ValueError(f"Unsupported key type: {key_type}")

class KeyFileManager:
    """
    Class for managing user keys stored in a YAML file.
    
    The YAML file structure is expected to have the following format:

    {
      "users": [
        {
          "name": "<USER_NAME>",
          "roles": ["admin@hostname", "another_role@host"],
          "keys": {
            "admin@hostname": {
              "rsa_private_key": "<RSA PRIVATE KEY PEM>",
              "rsa_public_key": "<RSA PUBLIC KEY PEM>",
              "ed25519_private_key": "<ED25519 PRIVATE KEY PEM>",
              "ed25519_public_key": "<ED25519 PUBLIC KEY PEM>",
              "sops_age_private_key": "<AGE PRIVATE KEY>",
              "sops_age_public_key": "<AGE PUBLIC KEY>",
              "created": "<TIMESTAMP>",
              "updated": "<TIMESTAMP>"
            }
          }
        }
      ]
    }
    """

    def __init__(self, file_path: str):
        """
        Initialize the manager with the path to the YAML file.

        Args:
            file_path (str): Path to the YAML file.
        """
        self.file_path = file_path
        self.data = self._load_file()
        self._validate_file_structure()

    # -------------------------------------------------------------------------
    # Public Methods
    # -------------------------------------------------------------------------

    def add_user(self, user_name: str) -> None:
        """
        Add a new user to the YAML file.

        Args:
            user_name (str): Name of the user to be added.

        Raises:
            ValueError: If the user already exists.
        """
        if any(user["name"] == user_name for user in self.data["users"]):
            raise ValueError(f"User '{user_name}' already exists.")

        new_user = {"name": user_name, "roles": [], "keys": {}}
        self.data["users"].append(new_user)
        self._save_file()

    def remove_user(self, user_name: str) -> None:
        """
        Remove a user from the YAML file.

        Args:
            user_name (str): Name of the user to be removed.
        """
        self.data["users"] = [
            user for user in self.data["users"] if user["name"] != user_name
        ]
        self._save_file()

    def add_user_role(self, user_name: str, role: str) -> None:
        """
        Add a role to an existing user.

        Args:
            user_name (str): Name of the user.
            role (str): Role name (e.g., 'admin@hostname').

        Raises:
            ValueError: If the role already exists for the user.
        """
        user = self._get_user(user_name)
        if role in user["roles"]:
            raise ValueError(f"Role '{role}' already exists for user '{user_name}'.")

        user["roles"].append(role)
        self._save_file()

    def remove_user_role(self, user_name: str, role: str) -> None:
        """
        Remove a role from an existing user and delete associated keys.

        Args:
            user_name (str): Name of the user.
            role (str): Role name (e.g., 'admin@hostname').
        """
        user = self._get_user(user_name)

        # Remove from the roles list
        if role in user["roles"]:
            user["roles"].remove(role)

        # Remove keys for this role if they exist
        user["keys"].pop(role, None)

        self._save_file()

    def add_user_key(
        self,
        user_name: str,
        role: str,
        key_type: str,
        private_key: str,
        public_key: str
    ) -> None:
        """
        Add a key for a user and role.

        Args:
            user_name (str): The name of the user.
            role (str): The role (e.g., 'admin@hostname').
            key_type (str): The key type ('rsa', 'ed25519', 'sops_age', etc.).
            private_key (str): The private key (PEM or raw text).
            public_key (str): The public key (PEM or raw text).

        Raises:
            ValueError: If the role does not exist for the user.
        """
        user = self._get_user(user_name)
        if role not in user["roles"]:
            raise ValueError(f"Role '{role}' does not exist for user '{user_name}'.")

        current_time = datetime.now().isoformat()
        if role not in user["keys"]:
            user["keys"][role] = {}

        user["keys"][role][f"{key_type}_private_key"] = private_key
        user["keys"][role][f"{key_type}_public_key"] = public_key
        user["keys"][role]["created"] = user["keys"][role].get("created", current_time)
        user["keys"][role]["updated"] = current_time

        self._save_file()

    def remove_user_key(
        self,
        user_name: str,
        role: str,
        key_type: str
    ) -> None:
        """
        Remove a key for a user and role.

        Args:
            user_name (str): The name of the user.
            role (str): The role (e.g., 'admin@hostname').
            key_type (str): The key type ('rsa', 'ed25519', 'sops_age', etc.).
        """
        user = self._get_user(user_name)
        if role in user["keys"]:
            user["keys"][role].pop(f"{key_type}_private_key", None)
            user["keys"][role].pop(f"{key_type}_public_key", None)

            if not user["keys"][role]:
                user["keys"].pop(role)

        self._save_file()

    def update_user_key(
        self,
        user_name: str,
        role: str,
        key_type: str,
        private_key: str,
        public_key: str
    ) -> None:
        """
        Update an existing key for a user and role.

        Args:
            user_name (str): The name of the user.
            role (str): The role (e.g., 'admin@hostname').
            key_type (str): The key type ('rsa', 'ed25519', 'sops_age', etc.).
            private_key (str): The private key (PEM or raw text).
            public_key (str): The public key (PEM or raw text).

        Raises:
            ValueError: If the role does not have any keys for the user.
        """
        user = self._get_user(user_name)
        if role not in user["keys"]:
            raise ValueError(
                f"Role '{role}' does not have keys for user '{user_name}'."
            )

        current_time = datetime.now().isoformat()
        user["keys"][role][f"{key_type}_private_key"] = private_key
        user["keys"][role][f"{key_type}_public_key"] = public_key
        user["keys"][role]["updated"] = current_time

        self._save_file()

    def auto_add_key(self, user_name: str, role: str, key_type: str) -> None:
        """
        Automatically generate and add a new key pair for a user and role.
        
        Args:
            user_name (str): The name of the user.
            role (str): The role (e.g., 'admin@hostname').
            key_type (str): The type of key to generate ('rsa' or 'ed25519').

        Raises:
            ValueError: If the role does not exist for the user.
        """
        user = self._get_user(user_name)
        if role not in user["roles"]:
            raise ValueError(f"Role '{role}' does not exist for user '{user_name}'.")

        private_key, public_key = generate_key_pair(key_type)

        current_time = datetime.now().isoformat()
        if role not in user["keys"]:
            user["keys"][role] = {}

        user["keys"][role][f"{key_type}_private_key"] = private_key
        user["keys"][role][f"{key_type}_public_key"] = public_key
        user["keys"][role]["created"] = current_time
        user["keys"][role]["updated"] = current_time

        self._save_file()

    def auto_update_key(self, user_name: str, role: str, key_type: str) -> None:
        """
        Automatically generate and update a key pair for a user and role.
        
        Args:
            user_name (str): The name of the user.
            role (str): The role (e.g., 'admin@hostname').
            key_type (str): The type of key to generate ('rsa' or 'ed25519').

        Raises:
            ValueError: If the role does not have any keys for the user.
        """
        user = self._get_user(user_name)
        if role not in user["keys"]:
            raise ValueError(
                f"Role '{role}' does not have keys for user '{user_name}'."
            )

        private_key, public_key = generate_key_pair(key_type)

        current_time = datetime.now().isoformat()
        user["keys"][role][f"{key_type}_private_key"] = private_key
        user["keys"][role][f"{key_type}_public_key"] = public_key
        user["keys"][role]["updated"] = current_time

        self._save_file()

    def get_users_data(self) -> list:
        """
        Extract all users, roles, and corresponding keys from the YAML file.

        Returns:
            list: A list of dictionaries containing user information.
        """
        users_data = []
        for user in self.data["users"]:
            users_data.append({
                "name": user["name"],
                "roles": user["roles"],
                "keys": user["keys"]
            })
        return users_data

    def generate_user_id_files(
        self,
        user_name: str,
        role_host: str,
        base_dir: str = "data/generated-user-folders"
    ) -> None:
        """
        Generate .ssh id files and deploy sops-age keys (both public and private) 
        for a specific user and role@host.

        Args:
            user_name (str): The name of the user.
            role_host (str): The role@host combination.
            base_dir (str): The base directory for user folders.

        Raises:
            ValueError: If no keys are found for the specified user and role@host.
        """
        user = self._get_user(user_name)
        role_keys = user["keys"].get(role_host)

        if not role_keys:
            raise ValueError(
                f"No keys found for user '{user_name}' and role '{role_host}'."
            )

        # Define the SSH directory and create it if necessary
        ssh_dir = Path(base_dir) / ".ssh" / role_host
        ssh_dir.mkdir(parents=True, exist_ok=True)

        # Generate SSH keys (RSA + Ed25519)
        handle_rsa_keys(role_keys, ssh_dir)
        handle_ed25519_keys(role_keys, ssh_dir)

        # Deploy SOPS Age keys
        deploy_sops_age_keys(role_keys, role_host, base_dir)

        print(
            f"Generated .ssh and .config/sops files for user '{user_name}' and role '{role_host}'."
        )

    def create_all_user_config_folders(self, base_dir: str = "data/generated-user-folders") -> None:
        """
        Iterate over all users and role@host combinations to generate config folders.

        Args:
            base_dir (str): The base directory for user folders.
        """
        for user in self.data["users"]:
            user_name = user["name"]
            for role_host in user["roles"]:
                try:
                    self.generate_user_id_files(user_name, role_host, base_dir)
                except ValueError as e:
                    print(f"Skipping {user_name} - {role_host}: {e}")

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _load_file(self) -> dict:
        """
        Load and parse the YAML file.

        Returns:
            dict: Parsed YAML file contents.

        Raises:
            FileNotFoundError: If the file is not found.
        """
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File not found: {self.file_path}")

        with open(self.file_path, 'r', encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _save_file(self) -> None:
        """
        Save the current data back to the YAML file.
        """
        with open(self.file_path, 'w', encoding="utf-8") as f:
            yaml.dump(self.data, f, default_flow_style=False)

    def _validate_file_structure(self) -> None:
        """
        Validate the structure of the loaded YAML file.

        Raises:
            ValueError: If the file structure is invalid.
        """
        if "users" not in self.data or not isinstance(self.data["users"], list):
            raise ValueError(
                "Invalid file structure: Missing or malformed 'users' key."
            )

        for user in self.data["users"]:
            if (
                "name" not in user
                or "roles" not in user
                or "keys" not in user
            ):
                raise ValueError(f"Invalid user structure: {user}")

            if (
                not isinstance(user["roles"], list)
                or not isinstance(user["keys"], dict)
            ):
                raise ValueError(
                    f"Invalid roles or keys structure for user: {user}"
                )

    def _get_user(self, user_name: str) -> dict:
        """
        Retrieve a user by name.

        Args:
            user_name (str): Name of the user.

        Raises:
            ValueError: If the user is not found.

        Returns:
            dict: The user dictionary.
        """
        for user in self.data["users"]:
            if user["name"] == user_name:
                return user
        raise ValueError(f"User '{user_name}' not found.")
