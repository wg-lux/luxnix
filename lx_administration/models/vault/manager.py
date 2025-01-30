from pydantic import BaseModel, model_validator
from typing import Optional, List, Union, Tuple, Dict
from pathlib import Path
from lx_administration.logging import get_logger
from lx_administration.yaml import dump_yaml, format_yaml, ansible_lint
from ..ansible import AnsibleInventory
from .config import (
    OWNER_TYPES,
    SECRET_TYPES,
    BASE_CLIENT_SECRET_TYPES,
    LOCAL_USER_SECRET_TYPES,
    yaml,
)
import warnings
from .psk import PreSharedKey
from .secret import Secret
from .secret_template import SecretTemplate
from .manager_utils import _get_by_name, _assert_unique_list
from datetime import datetime as dt, timedelta as td

from icecream import ic

from configparser import ConfigParser
import socket


class AnsibleCfgDefaults(BaseModel):
    inventory: str = "./ansible/inventory/hosts.ini"
    group_vars: str = "./ansible/inventory/group_vars"
    host_vars: str = "./ansible/inventory/host_vars"
    roles_path: str = "./ansible/roles"
    log_path: str = "./ansible/ansible.log"
    library: str = "./ansible/modules"
    vault_identity_list: Optional[str] = None

    def get_vid_list(self):
        if self.vault_identity_list:
            return self.vault_identity_list.split(",")
        else:
            return []

    def get_vid_dict(self):
        vid_list = self.get_vid_list()
        vid_dict = {}
        for vid in vid_list:
            # print(vid)
            host, path = vid.split("@")
            vid_dict[host] = path

        return vid_dict

    def vid_dict2list(self, vid_dict):
        vid_list = []
        for host, path in vid_dict.items():
            vid_list.append(f"{host}@{path}")
        return vid_list

    def vid_list2str(self, vid_list):
        return ",".join(vid_list)

    def update_vid_entry(self, host, path):
        vid_dict = self.get_vid_dict()
        vid_dict[host] = path
        vault_identity_list = self.vid_dict2list(vid_dict)
        self.vault_identity_list = self.vid_list2str(vault_identity_list)
        self.drop_missing_vid()

    def drop_missing_vid(self):
        file_not_found = []
        vid_dict = self.get_vid_dict()
        for host, path in vid_dict.items():
            if not Path(path).exists():
                file_not_found.append(host)

        for host in file_not_found:
            del vid_dict[host]

        self.vault_identity_list = self.vid_list2str(self.vid_dict2list(vid_dict))

        if file_not_found:
            ic(
                f"Removing vault_identities with missing files in ansible.cfg: {file_not_found}"
            )

    def validate(self):
        self.drop_missing_vid()


class AnsibleCfgPrivilegeEscalation(BaseModel):
    become: bool = True
    become_method: str = "sudo"
    become_user: str = "admin"
    become_ask_pass: bool = False

    def validate(self):
        pass


class AnsibleCfg(BaseModel):
    defaults: AnsibleCfgDefaults = AnsibleCfgDefaults()
    privilege_escalation: AnsibleCfgPrivilegeEscalation = (
        AnsibleCfgPrivilegeEscalation()
    )

    @classmethod
    def ensure_vault_id_pwdfile(cls, cfg_path: str, host: str, path: str):
        """Ensure vault_id and password_file entries in ansible.cfg"""
        host = host.replace("@", "_")
        path = path.replace("@", "_")
        ansible_cfg = cls.from_file(cfg_path)
        ansible_cfg.defaults.update_vid_entry(host, path)
        ansible_cfg.save_to_file(cfg_path)

    @classmethod
    def from_file(cls, file: str):
        """Load ansible.cfg file"""
        config = ConfigParser()
        config.read(file)

        # Convert ConfigParser to dict structure
        data = {"defaults": {}, "privilege_escalation": {}}

        if config.has_section("defaults"):
            data["defaults"] = dict(config["defaults"])

        if config.has_section("privilege_escalation"):
            # Convert string 'True'/'False' to boolean for boolean fields
            priv_esc = dict(config["privilege_escalation"])
            for key in ["become", "become_ask_pass"]:
                if key in priv_esc:
                    priv_esc[key] = config.getboolean("privilege_escalation", key)
            data["privilege_escalation"] = priv_esc

        return cls.model_validate(data)

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    def validate(self):
        """Validate ansible.cfg model"""
        self.defaults.validate()
        self.privilege_escalation.validate()

    def save_to_file(self, file: str):
        """Save ansible.cfg file"""
        config = ConfigParser()
        config["defaults"] = self.defaults.model_dump()
        config["privilege_escalation"] = self.privilege_escalation.model_dump()

        with open(file, "w") as f:
            config.write(f)


class Vault(BaseModel):
    """
    Primary Vault model, orchestrating secrets, keys, and inventory integration.
    """

    secrets: List[Secret] = []
    dir: str = "~/.lxv/"
    key: str = "~/.lxv.key"
    ansible_cfg_path: str = "./conf/ansible.cfg"
    owner_types: List[str] = OWNER_TYPES.copy()
    secret_types: List[str] = SECRET_TYPES.copy()
    default_client_secret_types: List[str] = BASE_CLIENT_SECRET_TYPES.copy()
    default_local_secret_types: List[str] = LOCAL_USER_SECRET_TYPES.copy()

    inventory: Optional[AnsibleInventory] = None
    default_system_users: List[str] = ["admin"]
    subnet: str = "172.16.255."
    secret_templates: List[SecretTemplate] = []
    pre_shared_keys: List[PreSharedKey] = []

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    @classmethod
    def _get_vault_paths(cls, dir: str, key: str) -> Union[Tuple[Path, Path, Path]]:
        """Get paths for vault configuration.

        This private method resolves and returns the necessary paths for vault operations:
        the directory path, key file path, and vault file path.

        Args:
            dir (str): Directory path where vault.yml will be located
            key (str): Path to the key file for encryption/decryption

        Returns:
            Union[Tuple[Path, Path, Path]]: A tuple containing:
                - dir (Path): Resolved directory path
                - key (Path): Resolved key file path
                - vault (Path): Path to vault.yml file

        Example:
            dir, key, vault = _get_vault_paths("~/vaults", "~/.ssh/id_rsa")
        """
        key = Path(key).expanduser().resolve()
        dir = Path(dir).expanduser().resolve()
        vault = dir / "vault.yml"

        return dir, key, vault

    @classmethod
    def load_dir(cls, vault_dir: str = "~/.lxv/", vault_key_path: str = "~/.lxv.key"):
        """
        Load a vault from a directory.

        This class method reads and validates vault data from a YAML file in the specified directory.

        Args:
            dir (str, optional): Path to the vault directory. Defaults to "~/.lxv/".
            key (str, optional): Path to the vault key file. Defaults to "~/.lxv.key".

        Returns:
            Vault: A validated Vault instance containing the loaded data.

        Raises:
            FileNotFoundError: If either the specified directory or vault file does not exist.

        Example:
            >>> vault = Vault.load_dir()
            >>> vault = Vault.load_dir("/custom/path/", "/custom/key.file")
        """

        logger = get_logger("Vaults-load_dir", reset=True)

        vault_dir_p, vault_key_path_p, vault_file_p = cls._get_vault_paths(
            vault_dir, vault_key_path
        )

        if not vault_dir_p.exists():
            raise FileNotFoundError(f"Directory {vault_dir} does not exist!")

        if not vault_file_p.exists():
            raise FileNotFoundError(f"File {vault_file_p} does not exist!")

        with open(vault_file_p, "r") as f:
            data = yaml.safe_load(f)

        if "secret_templates" in data and data["secret_templates"]:
            secret_templates = [
                SecretTemplate.model_validate(template)
                for template in data["secret_templates"]
            ]
            data["secret_templates"] = secret_templates

        if "pre_shared_keys" in data and data["pre_shared_keys"]:
            pre_shared_keys = [
                PreSharedKey.model_validate(psk) for psk in data["pre_shared_keys"]
            ]
            data["pre_shared_keys"] = pre_shared_keys

        if "secrets" in data and data["secrets"]:
            secrets = [Secret.model_validate(secret) for secret in data["secrets"]]
            data["secrets"] = secrets

        for key, value in data.items():
            logger.info(f"Loaded {key}:")
            if isinstance(value, list):
                for item in value:
                    logger.info(f"  - {item}")
            else:
                logger.info(f"  - {value}")

        # Let the model validator handle the conversion
        vault = cls(**data)
        return vault

    @classmethod
    def load_or_create(cls, dir: str = "~/.lxv/", key: str = "~/.lxv.key"):
        """
        Load an existing vault from disk or create a new one if not found.

        Args:
            dir (str): The directory path where the vault is stored.
            key (str): Path to the key file for decrypting the vault.

        Returns:
            Vault: The loaded or newly created vault.
        """
        dir, key, vault_file = cls._get_vault_paths(dir, key)

        if not vault_file.exists():
            ic("No vault file found. Creating new vault.")
            vault = cls()
            vault.save_to_file(vault_file)

        else:
            vault = cls.load_dir(dir, key)

        return vault

    def summary(self):
        """
        Generate a summary of the vault's contents.

        Returns:
            str: A formatted summary string containing the number of secrets, access keys, and templates.
        """
        return (
            "\n-------\n"
            f"Vault Summary:\n"
            f"Secrets: {len(self.secrets)}\n"
            f"Secret Templates: {len(self.secret_templates)}\n"
            f"Pre-Shared Keys: {len(self.pre_shared_keys)}\n"
            "-------\n"
        )

    def _validate_secret_templates(self):
        """
        Ensure all secret templates are unique by (name, owner_type) and then validate them.

        Raises:
            AssertionError: If duplicate templates or invalid fields are found.
        """
        name_owner_type_tuples = [
            (template.name, template.owner_type) for template in self.secret_templates
        ]
        _assert_unique_list(name_owner_type_tuples)

        for template in self.secret_templates:
            template.validate()

    def _validate_access_keys(self):
        # remove or comment out, since AccessKey no longer exists
        pass

    def _validate_secrets(self):
        """
        Validate all secrets within the vault.

        Raises:
            AssertionError: If any secret is invalid.
        """
        for secret in self.secrets:
            secret.validate()

    def validate(self):
        """
        Validate the vault by verifying secret templates, access keys, and secrets.

        Raises:
            AssertionError: If any template, access key, or secret is invalid.
        """
        self._validate_secret_templates()
        self._validate_access_keys()
        self._validate_secrets()

    def load_inventory(self, inventory_file: str):
        """
        Load Ansible inventory from a file.

        This method loads an Ansible inventory from the specified file path and assigns it
        to the instance's inventory attribute.

        Args:
            inventory_file (str): Path to the Ansible inventory file.

        Returns:
            AnsibleInventory: The loaded inventory object.

        Raises:
            AssertionError: If the specified inventory file does not exist.

        Example:
            inventory = manager.load_inventory("/path/to/inventory.yml")
        """
        assert Path(inventory_file).exists(), f"File {inventory_file} does not exist!"
        self.inventory = AnsibleInventory.from_file(inventory_file)
        return self.inventory

    def get_secret_template_by_name(self, name: str) -> Optional[SecretTemplate]:
        """
        Retrieves a secret template by its name from the available secret templates.

        Args:
            name (str): The name of the secret template to retrieve.

        Returns:
            SecretTemplate: The secret template object if found.
            None: If no template with the given name exists.

        Example:
            >>> manager.get_secret_template_by_name("ssh-key")
            <SecretTemplate: ssh-key>
        """
        return _get_by_name(self.secret_templates, name)

    def get_or_create_secret_template(
        self,
        name: str,
        owner_type: str,
        secret_type="password",
        vault_dir: str = "~/.lxv/",
    ) -> Tuple[SecretTemplate, bool]:
        """Get a secret template by name or create one if it doesn't exist.

        Args:
            name (str): Name of the secret template
            owner_type (str): Type of the owner for the template
            secret_type (str, optional): Type of secret. Defaults to "password"
            vault_dir (str, optional): Directory path for the vault. Defaults to "~/.lxv/"

        Returns:
            Tuple[SecretTemplate, bool]: A tuple containing:
                - SecretTemplate: The retrieved or newly created secret template
                - bool: True if a new template was created, False if existing template was found

        Example:
            >>> template, created = manager.get_or_create_secret_template("mysql", "database")
            >>> print(created)  # True if new template was created
        """
        template = self.get_secret_template_by_name(name)

        created = False
        if not template:
            template = SecretTemplate.create_secret_template(
                name=name,
                owner_type=owner_type,
                secret_type=secret_type,
                vault_dir=vault_dir,
            )
            self.secret_templates.append(template)
            created = True

        return template, created

    def get_or_create_secret_templates(
        self,
        names: List[str],
        owner_type: str,
        secret_type: str = "password",
        vault_dir: str = "~/.lxv/",
    ) -> Tuple[List[SecretTemplate], List[SecretTemplate]]:
        """
        Get or create multiple secret templates based on provided names.

        This method processes a list of template names and either retrieves existing templates
        or creates new ones if they don't exist.

        Args:
            names (List[str]): List of template names to get or create
            owner_type (str): Type of the owner for the templates
            secret_type (str, optional): Type of secret. Defaults to "password"
            vault_dir (str, optional): Directory path for the vault. Defaults to "~/.lxv/"

        Returns:
            Tuple[List[SecretTemplate], List[SecretTemplate]]: A tuple containing:
                - First list: All templates (both existing and newly created)
                - Second list: Only newly created templates

        Example:
            >>> templates, new_templates = get_or_create_secret_templates(
            ...     names=['template1', 'template2'],
            ...     owner_type='user'
            ... )
        """
        templates = []
        created_templates = []
        for name in names:
            template, created = self.get_or_create_secret_template(
                name, owner_type, secret_type, vault_dir
            )
            templates.append(template)
            if created:
                created_templates.append(template)

        return templates, created_templates

    def _sync_role_secret_templates(
        self,
    ) -> Tuple[List[SecretTemplate], List[SecretTemplate]]:
        """
        Synchronize and manage secret templates for roles.
        This method retrieves role names from inventory and creates or gets existing secret
        templates associated with those roles.
        Returns:
            Tuple[List[SecretTemplate], List[SecretTemplate]]: A tuple containing:
                - First list: All secret templates for roles (both existing and new)
                - Second list: Only newly created secret templates
        """
        # We Use password
        secret_type = "system_password"
        role_names = self.inventory.get_role_names()
        owner_type = "roles"
        _secret_templates, _created_secret_templates = (
            self.get_or_create_secret_templates(
                role_names, owner_type, secret_type=secret_type
            )
        )

        return _secret_templates, _created_secret_templates

    def _build_local_user_secret_templates(self, logger=None):
        """
        Builds secret templates for local users across all hosts in the inventory.

        This method creates or retrieves secret templates for both default system users and
        extra users defined per host. Templates are created for each combination of:
        - User (default system users + host-specific extra users)
        - Host (all hosts in inventory)
        - Secret type (defined in LOCAL_USER_SECRET_TYPES)

        Returns:
            tuple: A tuple containing two lists:
                - List of all secret templates (both existing and newly created)
                - List of only the newly created secret templates

        Templates are created with owner_type="local" and follow the naming pattern:
        "{username}@{hostname}"
        """
        if not logger:
            logger = get_logger("Vaults-build_local_user_secret_templates", reset=True)
        # make sure we fail if hardcoded owner_type is invalid due to other changes
        owner_type = "local"
        assert owner_type in OWNER_TYPES, f"Invalid owner_type: {owner_type}"

        secret_templates, created_secret_templates = [], []
        client_names = self.inventory.get_hostnames()
        default_users = self.default_system_users.copy()
        secret_types = LOCAL_USER_SECRET_TYPES

        for secret_type in secret_types:
            for client_name in client_names:
                client = self.inventory.get_host_by_name(client_name)
                extra_users = client.get_extra_user_names()

                users = extra_users + default_users
                user_secret_names = [f"{user}@{client_name}" for user in users]

                _secret_templates, _created_secret_templates = (
                    self.get_or_create_secret_templates(
                        user_secret_names, owner_type, secret_type
                    )
                )
                secret_templates.extend(_secret_templates)
                created_secret_templates.extend(_created_secret_templates)

        return secret_templates, created_secret_templates

    def _build_client_secret_templates(self):
        """
        Build secret templates for clients based on inventory hostnames and base client secret types.

        This method creates or retrieves secret templates for each combination of hostname and
        secret type defined in BASE_CLIENT_SECRET_TYPES for the 'clients' owner type.

        Returns:
            tuple: A tuple containing two lists:
                - secret_templates (list): All secret templates (existing and newly created)
                - created_secret_templates (list): Only newly created secret templates

        Raises:
            AssertionError: If owner_type is not in OWNER_TYPES

        Example:
            secret_templates, created_templates = vault._build_client_secret_templates()
        """
        secret_templates, created_secret_templates = [], []
        owner_type = "clients"
        secret_names = self.inventory.get_hostnames()
        secret_types = BASE_CLIENT_SECRET_TYPES

        assert owner_type in OWNER_TYPES, f"Invalid owner_type: {owner_type}"
        for secret_type in secret_types:
            _secret_templates, _created_secret_templates = (
                self.get_or_create_secret_templates(
                    secret_names, owner_type, secret_type
                )
            )
            secret_templates.extend(_secret_templates)
            created_secret_templates.extend(_created_secret_templates)

        return secret_templates, created_secret_templates

    def _sync_group_secret_templates(
        self,
    ) -> Tuple[List[SecretTemplate], List[SecretTemplate]]:
        """
        Synchronize and manage secret templates for groups.

        Returns:
            Tuple[List[SecretTemplate], List[SecretTemplate]]:
            - First list: All secret templates for groups (existing and new)
            - Second list: Only newly created secret templates
        """
        secret_type = "system_password"
        group_names = self.inventory.get_group_names()
        owner_type = "groups"
        _secret_templates, _created_secret_templates = (
            self.get_or_create_secret_templates(
                group_names, owner_type, secret_type=secret_type
            )
        )

        return _secret_templates, _created_secret_templates

    def sync_secret_templates(self, logger=None):
        if not logger:
            logger = get_logger("Vaults-sync_secret_templates", reset=True)

        secret_templates = []
        created_secret_templates = []

        # Get or create secret templates for roles
        _secret_templates, _created_secret_templates = (
            self._sync_role_secret_templates()
        )
        secret_templates.extend(_secret_templates)
        created_secret_templates.extend(_created_secret_templates)

        # Get or create secret templates for groups
        _secret_templates, _created_secret_templates = (
            self._sync_group_secret_templates()
        )
        secret_templates.extend(_secret_templates)
        created_secret_templates.extend(_created_secret_templates)

        # Get or create secret templates for local users
        _secret_templates, _created_secret_templates = (
            self._build_local_user_secret_templates()
        )
        secret_templates.extend(_secret_templates)
        created_secret_templates.extend(_created_secret_templates)

        for template in self.secret_templates:
            template.validate()
            _success = template.create_or_update_secrets(vault=self, logger=logger)

    def _sync_client_psk(self, logger=None) -> List[PreSharedKey]:
        """Create PSKs for all clients in inventory"""
        if not logger:
            logger = get_logger("Vaults-sync_client_psk")
        created_psks = []

        # Get all client hostnames from inventory
        client_names = self.inventory.get_hostnames()

        for client_name in client_names:
            psk, created = self.get_or_create_psk(client_name, logger)
            if created:
                created_psks.append(psk)
                # self.pre_shared_keys.append(psk)
                logger.info(f"Created new PSK for client {client_name}")

        return created_psks

    def sync_inventory(self, inventory_file: str, logger=None):
        """load inventory from file and sync templates and PSKs"""
        if not logger:
            logger = get_logger("Vaults-sync_inventory", reset=True)
        inventory_file: Path = Path(inventory_file)
        assert inventory_file.exists(), f"File {inventory_file} does not exist!"

        logger.info(f"Loading inventory from {inventory_file}")
        _inventory = self.load_inventory(inventory_file.resolve().as_posix())

        # First sync PSKs for all clients (hostnames)
        # TODO implement validity check and automated update
        # TODO implement archive of old PSKs
        created_psks = self._sync_client_psk(logger=logger)

        logger.info(f"Created {len(created_psks)} new pre-shared keys")
        for psk in created_psks:
            logger.info(f"Client PSK: {psk.name}")

        # # Then sync secret templates
        self.sync_secret_templates(logger=logger)

        self.save_to_file(logger=logger)

    def get_client_psk(self, client_name: str, logger=None) -> Optional[PreSharedKey]:
        """Get PSK for a specific client"""
        if not logger:
            logger = get_logger("Vaults-get_client_psk", reset=True)

        # First check in memory
        psk = _get_by_name(self.pre_shared_keys, client_name)
        if not psk:
            return None

        # Then verify file exists
        psk_path = Path(psk.file).expanduser().resolve()
        if not psk_path.exists():
            logger.warning(f"PSK file not found: {psk_path}")
            return None

        return psk

    def get_paths(self):
        """
        Retrieve the vault directory path, the key path, and the vault file path.

        Returns:
            Tuple[Path, Path, Path]: A tuple containing the directory path, key path, and vault file path.
        """
        return self._get_vault_paths(self.dir, self.key)

    def save_to_file(self, file: str = None, logger=None):
        """dump as yml"""
        if not logger:
            logger = get_logger("Vaults-save_to_file", reset=True)

        if not file:
            vault_dir, _vault_key, vault_file = self.get_paths()
        else:
            vault_file = Path(file).expanduser().resolve()
            vault_dir = vault_file.parent

        # Ensure all parent directories exist
        vault_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Saving vault to {vault_file}")

        # Convert model to dict with explicit path string conversion
        raw = self.model_dump(mode="json", exclude_none=True)

        # Handle PSK serialization
        if "pre_shared_keys" in raw and raw["pre_shared_keys"]:
            raw["pre_shared_keys"] = [
                psk.model_dump(mode="json", exclude_none=True)
                for psk in self.pre_shared_keys
            ]
            for psk in raw["pre_shared_keys"]:
                if "validity" in psk and isinstance(psk["validity"], (str, td)):
                    if isinstance(psk["validity"], td):
                        psk["validity"] = f"P{psk['validity'].days}D"

        logger.debug(raw.__repr__())

        # Use the dump_yaml function which now handles directory creation
        dump_yaml(raw, vault_file, format_yaml, ansible_lint)

    def ensure_vault_id(self, obj: PreSharedKey):
        conf_file = self.ansible_cfg_path
        host = obj.vault_id_prefix
        path = obj.file
        AnsibleCfg.ensure_vault_id_pwdfile(cfg_path=conf_file, host=host, path=path)

    def get_or_create_psk(self, name: str, logger=None) -> Tuple[PreSharedKey, bool]:
        """Get existing PSK or create new one"""
        if not logger:
            logger = get_logger("Vaults-get_or_create_psk", reset=True)

        existing_key = self.get_client_psk(name, logger)
        if existing_key:
            logger.info(f"Found existing PSK for client {name}")
            logger.info(f"PSK: {existing_key}")
            self.ensure_vault_id(existing_key)
            return existing_key, False

        logger.info(f"Creating new PSK for client {name}")
        psk_dir = Path(self.dir).expanduser().resolve() / "psk"
        psk_dir.mkdir(parents=True, exist_ok=True)
        psk = PreSharedKey.generate(name, psk_dir, logger)
        self.ensure_vault_id(psk)
        self.pre_shared_keys.append(psk)
        return psk, True

    def export_secrets_by_client(self, logger=None):
        """Export access keys for all hosts in the inventory."""
        from tqdm import tqdm
        import shutil

        if not logger:
            logger = get_logger("Vaults-export_secrets_by_client", reset=True)

        # Create deploy directory
        deploy_dir = Path(self.dir).expanduser().resolve() / "deploy"
        if deploy_dir.exists():
            shutil.rmtree(deploy_dir)
        deploy_dir.mkdir(parents=True, exist_ok=True)

        hostnames = self.inventory.get_hostnames()
        for hostname in tqdm(hostnames):
            logger.info(f"Exporting secrets for client: {hostname}")

            # Get PSK first and verify it exists
            psk = self.get_client_psk(hostname)
            if not psk:
                logger.error(f"No valid PSK found for host {hostname}, skipping...")
                continue

            psk_file = Path(psk.file)
            if not psk_file.exists():
                logger.error(f"PSK file not found: {psk_file}, skipping...")
                continue

            # Export keys for this host
            host_secrets = self.get_host_secrets(hostname)
            logger.info(f"Found {len(host_secrets)} secrets for host {hostname}")

            host_secret_dir = deploy_dir / hostname
            host_secret_dir.mkdir(parents=True, exist_ok=True)

            # Re-encrypt secrets using host's PSK
            for secret in tqdm(host_secrets):
                target_filename = secret.target_name
                target_path = host_secret_dir / target_filename
                try:
                    secret.create_re_encrypted_file(
                        target_path.as_posix(), psk_file.as_posix(), self
                    )
                except Exception as e:
                    logger.error(f"Failed to re-encrypt secret {secret.name}: {str(e)}")

    def get_local_hostname(self) -> str:
        return socket.gethostname()

    def get_vault_id_for_hostname(self, hostname: str) -> str:
        # Optionally parse self.ansible_cfg to find matching vault ID
        # For now, just return the hostname
        return hostname

    def get_local_vault_id(self) -> str:
        return self.get_vault_id_for_hostname(self.get_local_hostname())

    def get_local_psk(self) -> Optional[PreSharedKey]:
        return self.get_client_psk(self.get_local_hostname())

    def get_local_vault_id_with_path(self) -> str:
        return f"{self.get_local_hostname()}@{self.get_local_psk().file}"

    def _get_template_secrets(self, template_name: str) -> List[Secret]:
        """
        Get all secrets associated with a template by name.

        Args:
            template_name (str): Name of the template

        Returns:
            List[Secret]: List of secrets associated with the template

        Raises:
            ValueError: If any secret referenced by the template is not found
        """

        template = self.get_secret_template_by_name(template_name)
        assert template, f"Template '{template_name}' not found"

        secrets = []
        for secret_name in template.secret_names:
            secret = next((s for s in self.secrets if s.name == secret_name), None)
            if not secret:
                raise ValueError(
                    f"Secret '{secret_name}' referenced by template '{template_name}' not found"
                )
            secrets.append(secret)
        return secrets

    def get_secret_by_target_name(self, name: str) -> Optional[Secret]:
        from .manager_utils import _get_by_target_name

        secret = _get_by_target_name(self.secrets, name)
        assert secret, f"Secret '{name}' not found"

        return secret

    def get_host_secrets(self, hostname: str, logger=None) -> List[Secret]:
        """
        Determine which secrets belong to this host by checking roles, groups,
        or matching local/clients secrets with hostname.
        """
        if not logger:
            logger = get_logger("Vaults-get_host_secrets", reset=True)

        host = self.inventory.get_host_by_name(hostname)

        host_roles = host.ansible_role_names
        host_groups = host.ansible_group_names
        hostname = host.hostname

        logger.info("---------get_host_secrets---------")
        logger.info(f"Checking secrets for host: {hostname}")
        logger.info(f"Host roles: {host_roles}")
        logger.info(f"Host groups: {host_groups}")

        matched_secrets = []

        for st in self.secret_templates:
            logger.info(f"Checking template: {st.name}")
            logger.info(f"Owner type: {st.owner_type}")
            # logger.info(st.model_dump().__repr__())
            should_include = False
            if st.owner_type == "roles":
                # logger.info(f"Checking roles in roles for: {st.name}")
                if st.name in host_roles:
                    logger.info(f"Matched role: {st.name}")
                    should_include = True
            elif st.owner_type == "groups":
                logger.info(f"Checking groups in groups for: {st.name}")
                if st.name in host_groups:
                    logger.info(f"Matched group: {st.name}")
                    should_include = True
            elif st.owner_type in ("local", "clients"):
                logger.info(f"Checking local/client for: {st.name}")
                if st.name.endswith(f"@{hostname}"):
                    logger.info(f"Matched local/client: {st.name}")
                    should_include = True

            else:
                raise ValueError(f"Unknown owner_type: {st.owner_type}")

            if should_include:
                _secrets = self._get_template_secrets(st.name)
                logger.info(f"Matched secrets: {_secrets}")
                matched_secrets.extend(_secrets)

        # fetch hosts extra secrets
        extra_secret_names = host.extra_secret_names
        secrets = [self.get_secret_by_target_name(name) for name in extra_secret_names]

        matched_secrets.extend(secrets)

        return matched_secrets
