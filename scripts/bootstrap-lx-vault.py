#!/usr/bin/env python3
"""Initialize or refresh the local Luxnix vault setup."""

from __future__ import annotations

import argparse
import re
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
from lx_administration.models.ansible import AnsibleInventory, AnsibleInventoryHost
from lx_administration.models.vault.secret import _read_key, decrypt_secret
from lx_administration.password import PasswordGenerator
from lx_administration.permissions import ensure_private_directory

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
        "--admin-host",
        help="Rotate/export only this host's admin pair; requires --skip-sync",
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
    args = parser.parse_args(argv)
    if args.admin_host and (
        not args.skip_sync
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", args.admin_host)
    ):
        parser.error("--admin-host requires --skip-sync and a valid inventory hostname")
    return args


def _admin_scope(vault: Vault, hostname: str) -> Vault:
    """Select an exact pair without renewing or exporting unrelated credentials."""
    inventory = vault._require_inventory()
    if hostname not in inventory.get_hostnames():
        raise ValueError("Admin rotation host is absent from the vault inventory")
    psks = [psk for psk in vault.pre_shared_keys if psk.name == hostname]
    if len(psks) != 1:
        raise ValueError("Admin rotation requires one registered host PSK")
    _read_key(psks[0].file)
    template_name = f"admin@{hostname}"
    templates = [
        t
        for t in vault.secret_templates
        if t.name == template_name
        and t.owner_type == "local"
        and t.secret_type == "password"
    ]
    expected = {
        f"{template_name}_{suffix}": f"SCRT_local_password_admin_{suffix}"
        for suffix in ("password", "password_hash")
    }
    pair = [s for s in vault.secrets if s.name in expected]
    if (
        len(templates) != 1
        or len(pair) != 2
        or {s.name for s in pair} != set(expected)
        or set(templates[0].secret_names) != set(expected)
        or any(
            s.template_name != template_name
            or s.owner_type != "local"
            or s.secret_type != "password"
            or s.target_name != expected[s.name]
            for s in pair
        )
    ):
        raise ValueError("Admin rotation requires one canonical password/hash pair")
    scoped = vault.model_copy(deep=True)
    scoped.secrets = pair
    scoped.secret_templates = templates
    scoped.pre_shared_keys = psks
    scoped.inventory = AnsibleInventory(all=[AnsibleInventoryHost(hostname=hostname)])
    scoped.dir = str(Path(vault.dir) / "admin-rotations" / hostname)
    return scoped


def _validate_admin_scope(scoped: Vault) -> None:
    scoped.validate_vault()
    values = {
        s.target_name: decrypt_secret(s.file, scoped.key).decode("utf-8")
        for s in scoped.secrets
    }
    if not PasswordGenerator().verify_password_hash(
        values["SCRT_local_password_admin_password"],
        values["SCRT_local_password_admin_password_hash"],
    ):
        raise ValueError("Admin password/hash pair does not match")


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
    vault_key = Path(args.vault_key).expanduser().absolute()
    ansible_cfg_path = Path(args.ansible_cfg).expanduser().resolve()
    inventory_path = _resolve_inventory_path(args.inventory, args.autoconf_config)

    # Never create a replacement encryption key beside existing ciphertext.
    existing_vault = vault_dir.exists() and any(vault_dir.iterdir())
    if existing_vault and not (vault_dir / "vault.yml").is_file():
        raise ValueError(
            "Non-empty vault directory has no metadata; recover it before bootstrap"
        )
    if existing_vault and not vault_key.is_file():
        raise ValueError(
            "Existing vault has no master key; "
            "restore the verified key before bootstrap"
        )
    passwords = None
    if args.admin_passwords:
        passwords = load_admin_passwords(
            Path(args.admin_passwords).expanduser(), strict=True
        )
    if (
        args.admin_host
        and passwords is not None
        and set(passwords) != {args.admin_host}
    ):
        raise ValueError("Scoped input must contain exactly the selected admin host")
    if not args.skip_sync and not inventory_path.is_file():
        raise FileNotFoundError(f"Inventory file not found: {inventory_path}")

    if vault_key.exists() or vault_key.is_symlink():
        Vault(key=vault_key.as_posix()).validate_local_key()
    vault_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not existing_vault:
        ensure_local_vault_key(vault_key)

    vault = Vault.load_or_create(vault_dir.as_posix(), vault_key.as_posix())
    vault.dir = vault_dir.as_posix()
    vault.key = vault_key.as_posix()
    vault.validate_local_key()
    if args.admin_host:
        # Preflight the existing contract before any credential mutation. Expiry
        # is checked after replacement, so an expired account can be rotated.
        _admin_scope(vault, args.admin_host)
        if passwords is not None:
            import_admin_passwords(vault, passwords, logger=LOGGER)
        scoped = _admin_scope(vault, args.admin_host)
        _validate_admin_scope(scoped)
        vault.save_to_file(logger=LOGGER)
        if args.export:
            ensure_private_directory(scoped.dir)
            scoped.export_secrets_by_client(logger=LOGGER)
            LOGGER.info("Admin-only export: %s/deploy/%s", scoped.dir, args.admin_host)
        return
    _ensure_ansible_cfg(ansible_cfg_path, private_key_file="~/.ssh/id_ed25519")
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

    if passwords is not None:
        import_admin_passwords(vault, passwords, logger=LOGGER)

    vault.validate_vault()
    vault.save_to_file(logger=LOGGER)

    if args.export:
        LOGGER.info("Exporting secrets per host")
        vault.export_secrets_by_client(logger=LOGGER)

    LOGGER.info(vault.summary())


if __name__ == "__main__":
    main()
