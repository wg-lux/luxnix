#!/usr/bin/env python3
"""Initialize or refresh the local Luxnix vault setup."""

from __future__ import annotations

import argparse
from datetime import datetime as dt
from pathlib import Path
from typing import Dict, Iterable, Tuple

import yaml

from lx_administration.logging import get_logger
from lx_administration.models.vault.ansible_cfg import AnsibleCfg
from lx_administration.models.vault.manager import Vault
from lx_administration.models.vault.manager_utils import ensure_local_vault_key
from lx_administration.models.vault.secret import Secret
from lx_administration.password.generator import PasswordGenerator


LOGGER = get_logger("bootstrap-lx-vault", reset=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap the Luxnix vault setup")
    parser.add_argument(
        "--vault-dir",
        default="~/.lxv",
        help="Vault directory where secrets and PSKs will be stored",
    )
    parser.add_argument(
        "--vault-key",
        default="~/.lxv.key",
        help="Path to the local vault key used for encrypting secrets",
    )
    parser.add_argument(
        "--inventory",
        default="./autoconf/inventory.yml",
        help="Inventory file used to discover hosts, roles, and groups",
    )
    parser.add_argument(
        "--ansible-cfg",
        default="./conf/ansible.cfg",
        help="Path to the generated ansible.cfg file",
    )
    parser.add_argument(
        "--local-hostname",
        default=None,
        help=(
            "Override the hostname used for vault IDs. "
            "Defaults to the current machine hostname."
        ),
    )
    parser.add_argument(
        "--admin-passwords",
        default=None,
        help=(
            "Optional YAML file containing admin passwords keyed by inventory hostname. "
            "Passwords and their hashes will be imported into the vault."
        ),
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export re-encrypted secrets for hosts after bootstrapping",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip syncing the inventory (use only when vault already contains templates)",
    )
    return parser.parse_args()


def _ensure_ansible_cfg(ansible_cfg_path: Path, private_key_file: str) -> Path:
    template_path = Path("./conf/TEMPLATE_ansible.cfg")
    if ansible_cfg_path.exists():
        cfg = AnsibleCfg.from_file(ansible_cfg_path.as_posix())
    elif template_path.exists():
        cfg = AnsibleCfg.from_file(template_path.as_posix())
    else:
        cfg = AnsibleCfg()

    cfg.defaults.inventory = "./ansible/inventory/hosts.ini"
    cfg.defaults.group_vars = "./ansible/inventory/group_vars"
    cfg.defaults.host_vars = "./ansible/inventory/host_vars"
    cfg.defaults.roles_path = "./ansible/roles"
    cfg.defaults.library = "./ansible/modules"
    cfg.defaults.log_path = "./logs/ansible.log"
    cfg.defaults.private_key_file = private_key_file
    cfg.validate_cfg()

    ansible_cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.save_to_file(ansible_cfg_path.as_posix())
    return ansible_cfg_path


def _load_admin_passwords(path: Path) -> Dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not data:
        return {}
    if isinstance(data, dict):
        return data.get("admin_passwords", {}) or {}
    raise ValueError("Admin passwords file must contain a mapping under 'admin_passwords'.")


def _admin_secret_values(password: str, generator: PasswordGenerator) -> Iterable[Tuple[str, str]]:
    hashed = generator.create_password_hash(password)
    return ("password", password), ("password_hash", hashed)


def _import_admin_passwords(vault: Vault, passwords: Dict[str, str]) -> None:
    if not passwords:
        LOGGER.info("No admin passwords supplied; skipping import")
        return

    LOGGER.info("Importing %d admin passwords into the vault", len(passwords))
    generator = PasswordGenerator(mode="password", require_special=False)

    for hostname, password in passwords.items():
        if not password:
            LOGGER.warning("Hostname %s has an empty password entry; skipping", hostname)
            continue

        template_name = f"admin@{hostname}"
        template, _ = vault.get_or_create_secret_template(
            name=template_name,
            owner_type="local",
            secret_type="password",
            vault_dir=vault.dir,
        )

        secret_dir = Path(template.directory or "").expanduser()
        if not secret_dir:
            secret_dir = template.get_secret_dir(Path(vault.dir))
            template.directory = secret_dir.as_posix()
        secret_dir.mkdir(parents=True, exist_ok=True)

        for suffix, value in _admin_secret_values(password, generator):
            secret_name = f"{template.name}_{suffix}"
            secret_file = secret_dir / secret_name
            pseudo_secret_name = secret_name.replace(f"@{hostname}", "")
            target_name = (
                f"SCRT_{template.owner_type}_{template.secret_type}_{pseudo_secret_name}"
            )

            existing = next((s for s in vault.secrets if s.name == secret_name), None)
            if existing:
                existing.value = value
                existing.updated = dt.now()
                existing.update_file_encryption(vault)
                existing.value = None
            else:
                Secret.create_secret(value, secret_file.as_posix(), vault)
                secret = Secret(
                    name=secret_name,
                    template_name=template.name,
                    file=secret_file.as_posix(),
                    target_name=target_name,
                    owner_type=template.owner_type,
                    secret_type=template.secret_type,
                    local_vault_key=template.local_vault_key,
                    created=dt.now(),
                    updated=dt.now(),
                )
                vault.secrets.append(secret)

            if secret_name not in template.secret_names:
                template.secret_names.append(secret_name)


def main() -> None:
    args = _parse_args()

    vault_dir = Path(args.vault_dir).expanduser().resolve()
    vault_key = Path(args.vault_key).expanduser().resolve()
    ansible_cfg_path = Path(args.ansible_cfg).expanduser().resolve()
    inventory_path = Path(args.inventory).expanduser().resolve()

    vault_dir.mkdir(parents=True, exist_ok=True)
    ensure_local_vault_key(vault_key)
    _ensure_ansible_cfg(ansible_cfg_path, private_key_file="~/.ssh/id_ed25519")

    vault = Vault.load_or_create(vault_dir.as_posix(), vault_key.as_posix())
    vault.dir = vault_dir.as_posix()
    vault.key = vault_key.as_posix()
    vault.ansible_cfg_path = ansible_cfg_path.as_posix()

    if args.local_hostname:
        vault.local_hostname_override = args.local_hostname

    LOGGER.info("Using vault directory: %s", vault.dir)
    LOGGER.info("Using vault key: %s", vault.key)
    LOGGER.info("Using ansible.cfg: %s", vault.ansible_cfg_path)

    if not args.skip_sync:
        if not inventory_path.exists():
            raise FileNotFoundError(f"Inventory file not found: {inventory_path}")
        LOGGER.info("Syncing inventory from %s", inventory_path)
        vault.sync_inventory(inventory_path.as_posix(), logger=LOGGER)
    else:
        LOGGER.info("Skipping inventory sync as requested")

    local_host = args.local_hostname or vault.get_local_hostname()
    LOGGER.info("Ensuring PSK for local host: %s", local_host)
    vault.get_or_create_psk(local_host, logger=LOGGER)

    if args.admin_passwords:
        passwords_path = Path(args.admin_passwords).expanduser().resolve()
        if not passwords_path.exists():
            raise FileNotFoundError(
                f"Admin password file not found: {passwords_path}"
            )
        passwords = _load_admin_passwords(passwords_path)
        _import_admin_passwords(vault, passwords)

    vault.validate_vault()
    vault.save_to_file(logger=LOGGER)

    if args.export:
        LOGGER.info("Exporting secrets per host")
        vault.export_secrets_by_client(logger=LOGGER)

    LOGGER.info(vault.summary())


if __name__ == "__main__":
    main()
