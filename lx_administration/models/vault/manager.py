"""
Vault manager module for handling vault operations, secrets, and configuration.
"""

from datetime import timedelta as td
from pathlib import Path
import socket
from typing import Optional, List, Tuple, Dict, Any

from pydantic import BaseModel, Field
from pydantic import ConfigDict

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
from .psk import PreSharedKey
from .secret import Secret
from .secret_template import SecretTemplate
from .manager_utils import _get_by_name, _assert_unique_list, _get_by_target_name
from .ansible_cfg import AnsibleCfg


class Vault(BaseModel):
    """
    Primary Vault model, orchestrating secrets, keys, and inventory integration.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    secrets: List[Secret] = Field(default_factory=list)
    dir: str = "~/.lxv/"
    key: str = "~/.lxv.key"
    ansible_cfg_path: str = "./conf/ansible.cfg"
    owner_types: List[str] = Field(default_factory=lambda: OWNER_TYPES.copy())
    secret_types: List[str] = Field(default_factory=lambda: SECRET_TYPES.copy())
    default_client_secret_types: List[str] = Field(
        default_factory=lambda: BASE_CLIENT_SECRET_TYPES.copy()
    )
    default_local_secret_types: List[str] = Field(
        default_factory=lambda: LOCAL_USER_SECRET_TYPES.copy()
    )

    inventory: Optional[AnsibleInventory] = None
    default_system_users: List[str] = Field(default_factory=lambda: ["admin"])
    subnet: str = "172.16.255."
    secret_templates: List[SecretTemplate] = Field(default_factory=list)
    pre_shared_keys: List[PreSharedKey] = Field(default_factory=list)

    @classmethod
    def _get_vault_paths(cls, dir: str, key: str) -> Tuple[Path, Path, Path]:
        """Get paths for vault configuration.

        This private method resolves and returns the necessary paths for vault operations:
        the directory path, key file path, and vault file path.
        """
        key_path = Path(key).expanduser().resolve()
        dir_path = Path(dir).expanduser().resolve()
        vault_path = dir_path / "vault.yml"

        return dir_path, key_path, vault_path

    @classmethod
    def load_dir(cls, vault_dir: str = "~/.lxv/", vault_key_path: str = "~/.lxv.key"):
        """
        Load a vault from a directory.
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
            raw: Any = yaml.safe_load(f)
        data: Dict[str, Any]
        if isinstance(raw, dict):
            data = raw
        else:
            data = {}

        if data.get("secret_templates"):
            secret_templates = [
                SecretTemplate.model_validate(template)
                for template in data.get("secret_templates", [])
            ]
            data["secret_templates"] = secret_templates

        if data.get("pre_shared_keys"):
            pre_shared_keys = [
                PreSharedKey.model_validate(psk) for psk in data.get("pre_shared_keys", [])
            ]
            data["pre_shared_keys"] = pre_shared_keys

        if data.get("secrets"):
            secrets = [Secret.model_validate(secret) for secret in data.get("secrets", [])]
            data["secrets"] = secrets

        for key_name, value in data.items():
            logger.info(f"Loaded {key_name}:")
            if isinstance(value, list):
                for item in value:
                    logger.info(f"  - {item}")
            else:
                logger.info(f"  - {value}")

        # Let the model validator handle the conversion
        vault = cls.model_validate(data)
        return vault

    @classmethod
    def load_or_create(cls, dir: str = "~/.lxv/", key: str = "~/.lxv.key"):
        """
        Load an existing vault from disk or create a new one if not found.
        """
        dir_path, key_path, vault_file = cls._get_vault_paths(dir, key)

        if not vault_file.exists():
            logger = get_logger("Vaults-load_or_create", reset=True)
            logger.info("No vault file found. Creating new vault.")
            vault = cls()
            vault.save_to_file(vault_file.as_posix())

        else:
            vault = cls.load_dir(dir, key)

        return vault

    def summary(self):
        """Generate a summary of the vault's contents."""
        return (
            "\n-------\n"
            f"Vault Summary:\n"
            f"Secrets: {len(self.secrets)}\n"
            f"Secret Templates: {len(self.secret_templates)}\n"
            f"Pre-Shared Keys: {len(self.pre_shared_keys)}\n"
            "-------\n"
        )

    def _validate_secret_templates(self):
        """Ensure all secret templates are unique by (name, owner_type) and then validate them."""
        # Use a list of strings to satisfy Sequence[Hashable] for type checkers
        unique_keys = [
            f"{template.name}|{template.owner_type}" for template in self.secret_templates
        ]
        _assert_unique_list(unique_keys)

        for template in self.secret_templates:
            template.assert_valid()

    def _validate_secrets(self):
        """Validate all secrets within the vault."""
        for secret in self.secrets:
            secret.validate_secret()

    def validate_vault(self):
        """Validate the vault by verifying secret templates and secrets."""
        self._validate_secret_templates()
        self._validate_secrets()

    def load_inventory(self, inventory_file: str):
        """Load Ansible inventory from a file."""
        assert Path(inventory_file).exists(), f"File {inventory_file} does not exist!"
        self.inventory = AnsibleInventory.from_file(inventory_file)
        return self.inventory

    def get_secret_template_by_name(self, name: str) -> Optional[SecretTemplate]:
        """Retrieve a secret template by its name."""
        return _get_by_name(self.secret_templates, name)

    def get_or_create_secret_template(
        self,
        name: str,
        owner_type: str,
        secret_type="password",
        vault_dir: str = "~/.lxv/",
    ) -> Tuple[SecretTemplate, bool]:
        """Get a secret template by name or create one if it doesn't exist."""
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
        """Get or create multiple secret templates based on provided names."""
        templates: List[SecretTemplate] = []
        created_templates: List[SecretTemplate] = []
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
        """Synchronize and manage secret templates for roles."""
        secret_type = "system_password"
        assert self.inventory is not None, "Inventory must be loaded"
        role_names = self.inventory.get_role_names()
        owner_type = "roles"
        _secret_templates, _created_secret_templates = (
            self.get_or_create_secret_templates(
                role_names, owner_type, secret_type=secret_type
            )
        )

        return _secret_templates, _created_secret_templates

    def _build_local_user_secret_templates(self, logger=None):
        """Builds secret templates for local users across all hosts in the inventory."""
        if not logger:
            logger = get_logger("Vaults-build_local_user_secret_templates", reset=True)
        owner_type = "local"
        assert owner_type in OWNER_TYPES, f"Invalid owner_type: {owner_type}"

        secret_templates: List[SecretTemplate] = []
        created_secret_templates: List[SecretTemplate] = []
        assert self.inventory is not None, "Inventory must be loaded"
        client_names = [h for h in self.inventory.get_hostnames() if h is not None]
        default_users = self.default_system_users.copy()
        secret_types = LOCAL_USER_SECRET_TYPES

        for secret_type in secret_types:
            for client_name in client_names:
                client = self.inventory.get_host_by_name(client_name)
                assert client is not None, f"Unknown client {client_name}"
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
        """Build secret templates for clients based on inventory hostnames and base client secret types."""
        secret_templates: List[SecretTemplate] = []
        created_secret_templates: List[SecretTemplate] = []
        owner_type = "clients"
        assert self.inventory is not None, "Inventory must be loaded"
        secret_names = [h for h in self.inventory.get_hostnames() if h is not None]
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
        """Synchronize and manage secret templates for groups."""
        secret_type = "system_password"
        assert self.inventory is not None, "Inventory must be loaded"
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

        secret_templates: List[SecretTemplate] = []
        created_secret_templates: List[SecretTemplate] = []

        _secret_templates, _created_secret_templates = (
            self._sync_role_secret_templates()
        )
        secret_templates.extend(_secret_templates)
        created_secret_templates.extend(_created_secret_templates)

        _secret_templates, _created_secret_templates = (
            self._sync_group_secret_templates()
        )
        secret_templates.extend(_secret_templates)
        created_secret_templates.extend(_created_secret_templates)

        _secret_templates, _created_secret_templates = (
            self._build_local_user_secret_templates()
        )
        secret_templates.extend(_secret_templates)
        created_secret_templates.extend(_created_secret_templates)

        for template in self.secret_templates:
            template.assert_valid()
            _success = template.create_or_update_secrets(vault=self, logger=logger)

    def _sync_client_psk(self, logger=None) -> List[PreSharedKey]:
        """Create PSKs for all clients in inventory"""
        if not logger:
            logger = get_logger("Vaults-sync_client_psk")
        created_psks: List[PreSharedKey] = []

        assert self.inventory is not None, "Inventory must be loaded"
        client_names = [h for h in self.inventory.get_hostnames() if h is not None]

        for client_name in client_names:
            psk, created = self.get_or_create_psk(client_name, logger)
            if created:
                created_psks.append(psk)
                logger.info(f"Created new PSK for client {client_name}")

        return created_psks

    def sync_inventory(self, inventory_file: str, logger=None):
        """load inventory from file and sync templates and PSKs"""
        if not logger:
            logger = get_logger("Vaults-sync_inventory", reset=True)
        inventory_file_p: Path = Path(inventory_file)
        assert inventory_file_p.exists(), f"File {inventory_file} does not exist!"

        logger.info(f"Loading inventory from {inventory_file_p}")
        _inventory = self.load_inventory(inventory_file_p.resolve().as_posix())

        created_psks = self._sync_client_psk(logger=logger)

        logger.info(f"Created {len(created_psks)} new pre-shared keys")
        for psk in created_psks:
            logger.info(f"Client PSK: {psk.name}")

        self.sync_secret_templates(logger=logger)

        self.save_to_file(logger=logger)

    def get_client_psk(self, client_name: str, logger=None) -> Optional[PreSharedKey]:
        """Get PSK for a specific client"""
        if not logger:
            logger = get_logger("Vaults-get_client_psk", reset=True)

        psk = _get_by_name(self.pre_shared_keys, client_name)
        if not psk:
            return None

        psk_path = Path(psk.file).expanduser().resolve()
        if not psk_path.exists():
            logger.warning(f"PSK file not found: {psk_path}")
            return None

        return psk

    def get_paths(self) -> Tuple[Path, Path, Path]:
        """Retrieve the vault directory path, the key path, and the vault file path."""
        return self._get_vault_paths(self.dir, self.key)

    def save_to_file(self, file: Optional[str] = None, logger=None):
        """dump as yml"""
        if not logger:
            logger = get_logger("Vaults-save_to_file", reset=True)

        if not file:
            _vault_dir, _vault_key, vault_file = self.get_paths()
        else:
            vault_file = Path(file).expanduser().resolve()

        vault_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Saving vault to %s", vault_file)

        raw = self.model_dump(
            mode="json",
            exclude={"secrets": {"__all__": {"value"}}},
            exclude_none=True,
        )

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

        dump_yaml(raw, vault_file, format_yaml, ansible_lint)

    def ensure_vault_id(self, obj: PreSharedKey):
        conf_file = self.ansible_cfg_path
        host = obj.vault_id_prefix or obj.name
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
        try:
            _tmp = __import__("tqdm")
            tqdm = _tmp.tqdm.tqdm  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - optional dependency in typing
            def tqdm(x):
                return x
        import shutil

        if not logger:
            logger = get_logger("Vaults-export_secrets_by_client", reset=True)

        deploy_dir = Path(self.dir).expanduser().resolve() / "deploy"
        if deploy_dir.exists():
            shutil.rmtree(deploy_dir)
        deploy_dir.mkdir(parents=True, exist_ok=True)

        assert self.inventory is not None, "Inventory must be loaded"
        hostnames = [h for h in self.inventory.get_hostnames() if h is not None]
        for hostname in tqdm(hostnames):
            logger.info(f"Exporting secrets for client: {hostname}")

            psk = self.get_client_psk(hostname)
            if not psk:
                logger.error(f"No valid PSK found for host {hostname}, skipping...")
                continue

            psk_file = Path(psk.file)
            if not psk_file.exists():
                logger.error(f"PSK file not found: {psk_file}, skipping...")
                continue

            host_secrets = self.get_host_secrets(hostname)
            logger.info(f"Found {len(host_secrets)} secrets for host {hostname}")

            host_secret_dir = deploy_dir / hostname
            host_secret_dir.mkdir(parents=True, exist_ok=True)

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
        return hostname

    def get_local_vault_id(self) -> str:
        return self.get_vault_id_for_hostname(self.get_local_hostname())

    def get_local_psk(self) -> Optional[PreSharedKey]:
        return self.get_client_psk(self.get_local_hostname())

    def get_local_vault_id_with_path(self) -> str:
        psk = self.get_local_psk()
        assert psk is not None, "Local PSK not found"
        return f"{self.get_local_hostname()}@{psk.file}"

    def _get_template_secrets(self, template_name: str) -> List[Secret]:
        """Get all secrets associated with a template by name."""
        template = self.get_secret_template_by_name(template_name)
        assert template, f"Template '{template_name}' not found"

        secrets: List[Secret] = []
        for secret_name in template.secret_names:
            secret = next((s for s in self.secrets if s.name == secret_name), None)
            if not secret:
                raise ValueError(
                    f"Secret '{secret_name}' referenced by template '{template_name}' not found"
                )
            secrets.append(secret)
        return secrets

    def get_secret_by_target_name(self, name: str) -> Optional[Secret]:
        """Retrieve a secret by its target name from the vault's secrets."""
        secret = _get_by_target_name(self.secrets, name)
        assert secret, f"Secret '{name}' not found"
        return secret

    def get_host_secrets(self, hostname: str, logger=None) -> List[Secret]:
        """Determine which secrets belong to this host by checking roles, groups, or local/clients."""
        if not logger:
            logger = get_logger("Vaults-get_host_secrets", reset=True)

        assert self.inventory is not None, "Inventory must be loaded"
        host = self.inventory.get_host_by_name(hostname)
        assert host is not None, f"Unknown host {hostname}"

        host_roles = host.ansible_role_names
        host_groups = host.ansible_group_names
        hostname = host.hostname or hostname

        logger.info("---------get_host_secrets---------")
        logger.info("Checking secrets for host: %s", hostname)
        logger.info("Host roles: %s", host_roles)
        logger.info("Host groups: %s", host_groups)

        matched_secrets: List[Secret] = []

        for st in self.secret_templates:
            logger.info("Checking template: %s", st.name)
            logger.info("Owner type: %s", st.owner_type)
            should_include = False
            if st.owner_type == "roles":
                if st.name in host_roles:
                    logger.info("Matched role: %s", st.name)
                    should_include = True
            elif st.owner_type == "groups":
                logger.info("Checking groups in groups for: %s", st.name)
                if st.name in host_groups:
                    logger.info("Matched group: %s", st.name)
                    should_include = True
            elif st.owner_type in ("local", "clients"):
                logger.info("Checking local/client for: %s", st.name)
                if st.name.endswith(f"@{hostname}"):
                    logger.info("Matched local/client: %s", st.name)
                    should_include = True
            else:
                raise ValueError(f"Unknown owner_type: {st.owner_type}")

            if should_include:
                _secrets = self._get_template_secrets(st.name)
                logger.info("Matched secrets: %s", _secrets)
                matched_secrets.extend(_secrets)

        extra_secret_names = host.extra_secret_names
        extra_secrets: List[Secret] = []
        for name in extra_secret_names:
            s = self.get_secret_by_target_name(name)
            if s is not None:
                extra_secrets.append(s)
        matched_secrets.extend(extra_secrets)

        return matched_secrets

    def update_secret_value(
        self, secret_name: str, new_value: str, save_multiple: bool = False
    ):
        """Update the value of an existing secret and save the vault."""
        matching_secrets = [s for s in self.secrets if s.name == secret_name]

        if not matching_secrets:
            raise ValueError(f"Secret '{secret_name}' not found in vault.")

        if len(matching_secrets) > 1 and not save_multiple:
            raise ValueError(
                f"Multiple secrets found with name '{secret_name}'. Set save_multiple=True to update all."
            )

        for sec in matching_secrets:
            sec.value = new_value
            sec.update_file_encryption(self)

        self.save_to_file()
