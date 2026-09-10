"""
Vault manager module for handling vault operations, secrets, and configuration.
"""

import logging
import shutil
import socket
import tempfile
from collections.abc import Collection
from datetime import datetime
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from lx_administration.logging import get_logger
from lx_administration.permissions import ensure_private_directory
from lx_administration.utils.file_operations import advisory_file_lock
from lx_administration.yaml import (
    ansible_lint,
    dump_yaml,
    format_yaml,
    load_unique_yaml_file,
)

from ..ansible import AnsibleInventory
from .ansible_cfg import AnsibleCfg
from .config import (
    BASE_CLIENT_SECRET_TYPES,
    LOCAL_USER_SECRET_TYPES,
    OWNER_TYPES,
    SECRET_TYPES,
)
from .manager_utils import _assert_unique_list, _get_by_name, _get_by_target_name
from .psk import PreSharedKey
from .secret import Secret
from .secret_template import SecretTemplate


def _template_applies_to_host(
    template: SecretTemplate,
    *,
    hostname: str,
    role_names: Collection[str],
    group_names: Collection[str],
) -> bool:
    """Return whether a host-scoped template applies to one host."""
    match template.owner_type:
        case "roles":
            return template.name in role_names
        case "groups":
            return template.name in group_names
        case "local" | "clients":
            return template.name.endswith(f"@{hostname}")
        case owner_type:
            raise ValueError(f"Cannot match owner_type '{owner_type}' to a host")


class Vault(BaseModel):
    """
    Primary Vault model, orchestrating secrets, keys, and inventory integration.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    secrets: list[Secret] = Field(default_factory=list)
    dir: str = "~/.lxv/"
    key: str = "~/.lxv.key"
    ansible_cfg_path: str = "./conf/ansible.cfg"
    owner_types: list[str] = Field(default_factory=lambda: OWNER_TYPES.copy())
    secret_types: list[str] = Field(default_factory=lambda: SECRET_TYPES.copy())
    default_client_secret_types: list[str] = Field(
        default_factory=lambda: BASE_CLIENT_SECRET_TYPES.copy()
    )
    default_local_secret_types: list[str] = Field(
        default_factory=lambda: LOCAL_USER_SECRET_TYPES.copy()
    )

    inventory: AnsibleInventory | None = None
    default_system_users: list[str] = Field(default_factory=lambda: ["admin"])
    subnet: str = "172.16.255."
    secret_templates: list[SecretTemplate] = Field(default_factory=list)
    pre_shared_keys: list[PreSharedKey] = Field(default_factory=list)
    local_hostname_override: str | None = None

    @classmethod
    def _get_vault_paths(
        cls, vault_dir: str, vault_key: str
    ) -> tuple[Path, Path, Path]:
        """Get paths for vault configuration.

        This resolves the directory, key file, and vault file paths used by
        vault operations.
        """
        key_path = Path(vault_key).expanduser().absolute()
        dir_path = Path(vault_dir).expanduser().resolve()
        vault_path = dir_path / "vault.yml"

        return dir_path, key_path, vault_path

    @classmethod
    def load_dir(
        cls,
        vault_dir: str = "~/.lxv/",
        vault_key_path: str = "~/.lxv.key",
    ) -> Self:
        """Load a vault from a directory."""

        logger = get_logger("Vaults-load_dir", reset=True)

        vault_dir_p, _, vault_file_p = cls._get_vault_paths(vault_dir, vault_key_path)

        if not vault_dir_p.exists():
            raise FileNotFoundError(f"Directory {vault_dir} does not exist!")

        if not vault_file_p.exists():
            raise FileNotFoundError(f"File {vault_file_p} does not exist!")

        raw: object = load_unique_yaml_file(vault_file_p)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected a YAML mapping in {vault_file_p}")

        vault = cls.model_validate(raw)
        vault.dir = vault_dir_p.as_posix()
        vault.key = cls._get_vault_paths(vault_dir, vault_key_path)[1].as_posix()

        logger.info(
            "Loaded vault metadata: secrets=%d, templates=%d, pre_shared_keys=%d",
            len(vault.secrets),
            len(vault.secret_templates),
            len(vault.pre_shared_keys),
        )

        return vault

    @classmethod
    def load_or_create(
        cls,
        dir: str = "~/.lxv/",
        key: str = "~/.lxv.key",
    ) -> Self:
        """Load an existing vault or create one with the requested paths."""
        dir_path, key_path, vault_file = cls._get_vault_paths(dir, key)

        if not vault_file.exists():
            logger = get_logger("Vaults-load_or_create", reset=True)
            logger.info("No vault file found. Creating new vault.")
            vault = cls(dir=dir_path.as_posix(), key=key_path.as_posix())
            vault.save_to_file(vault_file.as_posix())

        else:
            vault = cls.load_dir(dir, key)

        return vault

    def summary(self) -> str:
        """Generate a summary of the vault's contents."""
        return (
            "\n-------\n"
            f"Vault Summary:\n"
            f"Secrets: {len(self.secrets)}\n"
            f"Secret Templates: {len(self.secret_templates)}\n"
            f"Pre-Shared Keys: {len(self.pre_shared_keys)}\n"
            "-------\n"
        )

    def _validate_secret_templates(self) -> None:
        """Validate templates uniquely by name and owner type."""
        # Use a list of strings to satisfy Sequence[Hashable] for type checkers
        unique_keys = [
            f"{template.name}|{template.owner_type}"
            for template in self.secret_templates
        ]
        _assert_unique_list(unique_keys)

        for template in self.secret_templates:
            template.assert_valid()

    def _validate_secrets(self) -> None:
        """Validate all secrets within the vault."""
        for secret in self.secrets:
            secret.validate_secret()

    def validate_vault(self) -> None:
        """Validate the vault by verifying secret templates and secrets."""
        self._validate_secret_templates()
        self._validate_secrets()

    def load_inventory(self, inventory_file: str | Path) -> AnsibleInventory:
        """Load Ansible inventory from a file."""
        inventory_path = Path(inventory_file).expanduser().resolve()
        if not inventory_path.exists():
            raise FileNotFoundError(f"Inventory file does not exist: {inventory_path}")

        self.inventory = AnsibleInventory.from_file(inventory_path.as_posix())
        return self.inventory

    def _require_inventory(self) -> AnsibleInventory:
        """Return the loaded inventory or raise a stable configuration error."""
        if self.inventory is None:
            raise ValueError("Inventory must be loaded")
        return self.inventory

    def get_secret_template_by_name(self, name: str) -> SecretTemplate | None:
        """Retrieve a secret template by its name."""
        return _get_by_name(self.secret_templates, name)

    def get_or_create_secret_template(
        self,
        name: str,
        owner_type: str,
        secret_type: str = "password",
        vault_dir: str | None = None,
    ) -> tuple[SecretTemplate, bool]:
        """Get a secret template by name or create one if it doesn't exist."""
        template = self.get_secret_template_by_name(name)

        created = False
        if not template:
            template = SecretTemplate.create_secret_template(
                name=name,
                owner_type=owner_type,
                secret_type=secret_type,
                vault_dir=vault_dir or self.dir,
            )
            self.secret_templates.append(template)
            created = True

        return template, created

    def get_or_create_secret_templates(
        self,
        names: list[str],
        owner_type: str,
        secret_type: str = "password",
        vault_dir: str | None = None,
    ) -> tuple[list[SecretTemplate], list[SecretTemplate]]:
        """Get or create multiple secret templates based on provided names."""
        templates: list[SecretTemplate] = []
        created_templates: list[SecretTemplate] = []
        for name in names:
            template, created = self.get_or_create_secret_template(
                name, owner_type, secret_type, vault_dir
            )
            templates.append(template)
            if created:
                created_templates.append(template)

        return templates, created_templates

    def _sync_role_secret_templates(self) -> None:
        """Ensure a system-password template exists for every role."""
        secret_type = "system_password"
        inventory = self._require_inventory()
        role_names = inventory.get_role_names()
        owner_type = "roles"
        self.get_or_create_secret_templates(
            role_names, owner_type, secret_type=secret_type
        )

    def _build_local_user_secret_templates(self) -> None:
        """Ensure local-user templates exist for every client."""
        owner_type = "local"

        inventory = self._require_inventory()
        client_names = [h for h in inventory.get_hostnames() if h is not None]
        default_users = self.default_system_users.copy()
        secret_types = LOCAL_USER_SECRET_TYPES

        for secret_type in secret_types:
            for client_name in client_names:
                client = inventory.get_host_by_name(client_name)
                if client is None:
                    raise ValueError(f"Unknown client {client_name}")
                extra_users = client.get_extra_user_names()

                users = extra_users + default_users
                user_secret_names = [f"{user}@{client_name}" for user in users]

                self.get_or_create_secret_templates(
                    user_secret_names, owner_type, secret_type
                )

    def _sync_group_secret_templates(self) -> None:
        """Ensure a system-password template exists for every group."""
        secret_type = "system_password"
        inventory = self._require_inventory()
        group_names = inventory.get_group_names()
        owner_type = "groups"
        self.get_or_create_secret_templates(
            group_names, owner_type, secret_type=secret_type
        )

    def sync_secret_templates(self, logger: logging.Logger | None = None) -> None:
        """Synchronize template metadata and materialize its secrets."""
        if not logger:
            logger = get_logger("Vaults-sync_secret_templates", reset=True)

        self._sync_role_secret_templates()
        self._sync_group_secret_templates()
        self._build_local_user_secret_templates()

        for template in self.secret_templates:
            template.assert_valid()
            template.create_or_update_secrets(vault=self, logger=logger)

    def _sync_client_psk(
        self, logger: logging.Logger | None = None
    ) -> list[PreSharedKey]:
        """Create PSKs for all clients in inventory."""
        if not logger:
            logger = get_logger("Vaults-sync_client_psk")
        created_psks: list[PreSharedKey] = []

        inventory = self._require_inventory()
        client_names = [h for h in inventory.get_hostnames() if h is not None]

        for client_name in client_names:
            psk, created = self.get_or_create_psk(client_name, logger)
            if created:
                created_psks.append(psk)
                logger.info("Created new PSK for client %s", client_name)

        return created_psks

    def sync_inventory(
        self,
        inventory_file: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        """Load inventory, then synchronize PSKs, templates, and secrets."""
        if not logger:
            logger = get_logger("Vaults-sync_inventory", reset=True)

        logger.info("Loading inventory from %s", inventory_file)
        self.load_inventory(inventory_file)

        created_psks = self._sync_client_psk(logger=logger)

        logger.info("Created %d new pre-shared key(s)", len(created_psks))
        for psk in created_psks:
            logger.info("Client PSK: %s", psk.name)

        self.sync_secret_templates(logger=logger)

        self.save_to_file(logger=logger)

    def get_client_psk(
        self,
        client_name: str,
        logger: logging.Logger | None = None,
    ) -> PreSharedKey | None:
        """Return a client's PSK when its file exists."""
        if not logger:
            logger = get_logger("Vaults-get_client_psk", reset=True)

        psk = _get_by_name(self.pre_shared_keys, client_name)
        if not psk:
            return None

        psk_path = Path(psk.file).expanduser().resolve()
        if not psk_path.exists():
            logger.warning("PSK file not found: %s", psk_path)
            return None

        return psk

    def get_paths(self) -> tuple[Path, Path, Path]:
        """Retrieve the vault directory path, the key path, and the vault file path."""
        return self._get_vault_paths(self.dir, self.key)

    def save_to_file(
        self,
        file: str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Save public vault metadata as YAML."""
        if not logger:
            logger = get_logger("Vaults-save_to_file", reset=True)

        if not file:
            vault_file = self.get_paths()[2]
        else:
            vault_file = Path(file).expanduser().resolve()

        vault_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Saving vault to %s", vault_file)

        raw = self.model_dump(
            mode="json",
            exclude={"secrets": {"__all__": {"value"}}},
            exclude_none=True,
        )

        dump_yaml(raw, vault_file, format_yaml, ansible_lint)

    def ensure_vault_id(self, obj: PreSharedKey) -> None:
        conf_file = self.ansible_cfg_path
        host = obj.vault_id_prefix or obj.name
        path = obj.file
        AnsibleCfg.ensure_vault_id_pwdfile(cfg_path=conf_file, host=host, path=path)

    def get_or_create_psk(
        self,
        name: str,
        logger: logging.Logger | None = None,
    ) -> tuple[PreSharedKey, bool]:
        """Return an existing PSK or create one."""
        if not logger:
            logger = get_logger("Vaults-get_or_create_psk", reset=True)

        existing_key = self.get_client_psk(name, logger)
        if existing_key:
            logger.info("Found existing PSK for client %s", name)
            self.ensure_vault_id(existing_key)
            return existing_key, False

        logger.info("Creating new PSK for client %s", name)
        psk_dir = Path(self.dir).expanduser().resolve() / "psk"
        psk_dir.mkdir(parents=True, exist_ok=True)
        psk = PreSharedKey.generate(name, psk_dir)
        self.ensure_vault_id(psk)
        self.pre_shared_keys.append(psk)
        return psk, True

    def export_secrets_by_client(self, logger: logging.Logger | None = None) -> None:
        """Re-encrypt each host's secrets with that host's PSK."""
        if not logger:
            logger = get_logger("Vaults-export_secrets_by_client", reset=True)

        inventory = self._require_inventory()
        vault_dir = Path(self.dir).expanduser().resolve()
        ensure_private_directory(vault_dir)
        with advisory_file_lock(
            lock_path=vault_dir / ".export.lock", timeout_seconds=0
        ):
            self._export_secrets_locked(vault_dir, inventory, logger)

    def _export_secrets_locked(self, vault_dir, inventory, logger) -> None:
        deploy_dir = vault_dir / "deploy"
        previous = vault_dir / ".deploy-previous"
        if previous.exists() or previous.is_symlink():
            raise ValueError(
                "Interrupted export recovery required: .deploy-previous exists"
            )
        if deploy_dir.is_symlink() or (deploy_dir.exists() and not deploy_dir.is_dir()):
            raise ValueError("Export destination must be a regular directory")
        # Keep the last complete export until every replacement has encrypted.
        with tempfile.TemporaryDirectory(prefix=".export-", dir=vault_dir) as temporary:
            stage = Path(temporary) / "deploy"
            stage.mkdir(mode=0o700)
            self._render_client_exports(stage, inventory, logger)
            if deploy_dir.exists():
                deploy_dir.rename(previous)
            try:
                stage.rename(deploy_dir)
            except OSError:
                if previous.exists():
                    previous.rename(deploy_dir)
                raise
            if previous.exists():
                shutil.rmtree(previous)

    def _render_client_exports(self, deploy_dir, inventory, logger) -> None:
        hostnames = [h for h in inventory.get_hostnames() if h is not None]
        for hostname in hostnames:
            if (
                not hostname
                or Path(hostname).name != hostname
                or hostname in (".", "..")
            ):
                raise ValueError("Invalid export hostname")
            logger.info("Exporting secrets for client: %s", hostname)

            psk = self.get_client_psk(hostname, logger)
            if not psk:
                raise ValueError(f"No valid PSK found for host {hostname}")

            psk_file = Path(psk.file)
            if not psk_file.is_file() or psk_file.stat().st_size == 0:
                raise ValueError(f"Missing or empty PSK for host {hostname}")

            host_secrets = self.get_host_secrets(hostname, logger)
            logger.info("Found %d secret(s) for host %s", len(host_secrets), hostname)

            host_secret_dir = deploy_dir / hostname
            host_secret_dir.mkdir(mode=0o700)

            targets = set()
            for secret in host_secrets:
                if (
                    not secret.target_name
                    or Path(secret.target_name).name != secret.target_name
                    or secret.target_name in (".", "..")
                    or secret.target_name in targets
                ):
                    raise ValueError(
                        f"Invalid or duplicate secret export target for {hostname}"
                    )
                targets.add(secret.target_name)
                target_path = host_secret_dir / secret.target_name
                try:
                    secret.create_re_encrypted_file(
                        target_path.as_posix(), psk_file.as_posix(), self
                    )
                except Exception:
                    raise RuntimeError(
                        f"Secret export failed for host {hostname}"
                    ) from None

    def get_local_hostname(self) -> str:
        if self.local_hostname_override:
            return self.local_hostname_override
        return socket.gethostname()

    def get_vault_id_for_hostname(self, hostname: str) -> str:
        return hostname

    def get_master_vault_id(self) -> str:
        from .secret import MASTER_VAULT_ID

        return MASTER_VAULT_ID

    def validate_local_key(self) -> None:
        """Fail before writes when any stored secret cannot use the declared key."""
        from .secret import _read_key, decrypt_secret

        _read_key(self.key)
        for secret in self.secrets:
            decrypt_secret(secret.file, self.key)

    def get_local_vault_id(self) -> str:
        return self.get_vault_id_for_hostname(self.get_local_hostname())

    def get_local_psk(self) -> PreSharedKey | None:
        return self.get_client_psk(self.get_local_hostname())

    def get_local_vault_id_with_path(self) -> str:
        psk = self.get_local_psk()
        if psk is None:
            raise ValueError("Local PSK not found")
        return f"{self.get_local_hostname()}@{psk.file}"

    def _get_template_secrets(self, template_name: str) -> list[Secret]:
        """Get all secrets associated with a template by name."""
        template = self.get_secret_template_by_name(template_name)
        if template is None:
            raise ValueError(f"Template '{template_name}' not found")

        secrets: list[Secret] = []
        for secret_name in template.secret_names:
            secret = next((s for s in self.secrets if s.name == secret_name), None)
            if secret is None:
                raise ValueError(
                    f"Secret '{secret_name}' referenced by template "
                    f"'{template_name}' not found"
                )
            secrets.append(secret)
        return secrets

    def get_secret_by_target_name(self, name: str) -> Secret:
        """Return the secret with the requested target name."""
        secret = _get_by_target_name(self.secrets, name)
        if secret is None:
            raise ValueError(f"Secret '{name}' not found")
        return secret

    def get_host_secrets(
        self,
        hostname: str,
        logger: logging.Logger | None = None,
    ) -> list[Secret]:
        """Find host secrets through role, group, local, and client templates."""
        if not logger:
            logger = get_logger("Vaults-get_host_secrets", reset=True)

        inventory = self._require_inventory()
        host = inventory.get_host_by_name(hostname)
        if host is None:
            raise ValueError(f"Unknown host {hostname}")

        role_names = host.ansible_role_names
        group_names = host.ansible_group_names
        hostname = host.hostname or hostname

        logger.info(
            "Checking secrets for host %s (roles=%s, groups=%s)",
            hostname,
            role_names,
            group_names,
        )

        matched_secrets: list[Secret] = []

        for template in self.secret_templates:
            if not _template_applies_to_host(
                template,
                hostname=hostname,
                role_names=role_names,
                group_names=group_names,
            ):
                continue

            template_secrets = self._get_template_secrets(template.name)
            logger.info(
                "Matched template %s with %d secret(s)",
                template.name,
                len(template_secrets),
            )
            matched_secrets.extend(template_secrets)

        for target_name in host.extra_secret_names:
            secret = self.get_secret_by_target_name(target_name)
            matched_secrets.append(secret)

        return matched_secrets

    def update_secret_value(
        self, secret_name: str, new_value: str, save_multiple: bool = False
    ) -> None:
        """Update the value of an existing secret and save the vault."""
        matching_secrets = [s for s in self.secrets if s.name == secret_name]

        if not matching_secrets:
            raise ValueError(f"Secret '{secret_name}' not found in vault.")

        if len(matching_secrets) > 1 and not save_multiple:
            raise ValueError(
                f"Multiple secrets found with name '{secret_name}'. "
                "Set save_multiple=True to update all."
            )

        for sec in matching_secrets:
            if sec.secret_type in ("password", "system_password") and any(
                s.template_name == sec.template_name
                and s.name.endswith("_password_hash")
                for s in self.secrets
            ):
                raise ValueError(
                    "Paired password/hash secrets require coordinated rotation; "
                    "use the admin-password import workflow for admin accounts"
                )

        for sec in matching_secrets:
            sec.value = new_value
            try:
                sec.update_file_encryption(self)
                sec.updated = datetime.now()
            finally:
                sec.value = None

        self.save_to_file()
