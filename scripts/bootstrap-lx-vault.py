#!/usr/bin/env python3
"""Initialize or refresh the local Luxnix vault setup."""

from __future__ import annotations

import argparse
from pathlib import Path

from lx_administration.autoconf import AutoconfConfig, DEFAULT_CONFIG_PATH
from lx_administration.logging import get_logger
from lx_administration.models.vault import (
    AnsibleCfg,
    Vault,
    import_admin_passwords,
    load_admin_passwords,
)
from lx_administration.models.vault.manager_utils import ensure_local_vault_key

LOGGER = get_logger("bootstrap-lx-vault", reset=True)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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
        type=Path,
        default=None,
        help=(
            "Inventory file used to discover hosts, roles, and groups; "
            "defaults to the configured Autoconf output inventory"
        ),
    )
    parser.add_argument(
        "--autoconf-config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Autoconf configuration file (default: {DEFAULT_CONFIG_PATH})",
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
            "Optional YAML file containing admin passwords keyed by "
            "inventory hostname. "
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
        help=(
            "Skip syncing the inventory (use only when the vault already "
            "contains templates)"
        ),
    )
    return parser.parse_args(argv)


def _resolve_inventory_path(
    inventory: Path | None,
    autoconf_config: Path,
) -> Path:
    """Resolve an explicit inventory or derive it from central Autoconf options."""
    if inventory is not None:
        return inventory.expanduser().resolve()
    return AutoconfConfig.load(autoconf_config).output_layout.inventory_file


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


def main() -> None:
    args = _parse_args()

    vault_dir = Path(args.vault_dir).expanduser().resolve()
    vault_key = Path(args.vault_key).expanduser().resolve()
    ansible_cfg_path = Path(args.ansible_cfg).expanduser().resolve()
    inventory_path = _resolve_inventory_path(args.inventory, args.autoconf_config)

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
        passwords = load_admin_passwords(passwords_path)
        import_admin_passwords(vault, passwords, logger=LOGGER)

    vault.validate_vault()
    vault.save_to_file(logger=LOGGER)

    if args.export:
        LOGGER.info("Exporting secrets per host")
        vault.export_secrets_by_client(logger=LOGGER)

    LOGGER.info(vault.summary())


if __name__ == "__main__":
    main()
