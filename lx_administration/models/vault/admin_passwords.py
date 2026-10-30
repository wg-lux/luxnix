"""Load local admin-password files and import them into a Vault."""

import logging
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from lx_administration.logging import get_logger
from lx_administration.yaml import load_unique_yaml_file

from ...password import PasswordGenerator
from .secret import Secret
from .secret_template import SecretTemplate

if TYPE_CHECKING:
    from .manager import Vault


def load_admin_passwords(path: str | Path, *, strict: bool = False) -> dict[str, str]:
    """Load hostname/password pairs without exposing their values in errors."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"Admin password file not found: {source}")
    if strict and (source.is_symlink() or stat.S_IMODE(source.stat().st_mode) & 0o077):
        raise ValueError(
            "Admin password source must be a private regular non-symlink file"
        )

    data = load_unique_yaml_file(source)
    if data is None and not strict:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Admin password file must be a YAML mapping")

    passwords = data.get("admin_passwords") or {}
    if not isinstance(passwords, dict):
        raise ValueError("'admin_passwords' must be a YAML mapping")
    if strict:
        _validate_password_mapping(passwords)

    return {
        str(hostname): str(password)
        for hostname, password in passwords.items()
        if password is not None
    }


def _validate_password_mapping(passwords: dict[str, str]) -> None:
    if not passwords:
        raise ValueError("Admin password mapping must not be empty")
    for hostname, password in passwords.items():
        if not isinstance(hostname, str) or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", hostname
        ):
            raise ValueError("Admin password mapping contains an invalid hostname")
        if not isinstance(password, str) or not password.strip():
            raise ValueError(
                "Admin password mapping requires non-empty string passwords"
            )


def _admin_secret_values(
    password: str,
    generator: PasswordGenerator,
) -> tuple[tuple[str, str], tuple[str, str]]:
    return (
        ("password", password),
        ("password_hash", generator.create_password_hash(password)),
    )


def _secret_directory(template: SecretTemplate, vault: "Vault") -> Path:
    if template.directory is None:
        directory = template.get_secret_dir(vault.dir)
        template.directory = directory.as_posix()
    else:
        directory = Path(template.directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _update_secret(secret: Secret, value: str, vault: "Vault") -> None:
    secret.value = value
    secret.updated = datetime.now()
    try:
        secret.update_file_encryption(vault)
    finally:
        secret.value = None


def import_admin_passwords(
    vault: "Vault",
    passwords: dict[str, str],
    logger: logging.Logger | None = None,
) -> None:
    """Create or update admin password and password-hash secrets."""
    logger = logger or get_logger("import-admin-passwords")
    if not passwords:
        logger.info("No admin passwords supplied; skipping import")
        return

    _validate_password_mapping(passwords)
    if vault.inventory is not None:
        unknown = set(passwords) - set(vault.inventory.get_hostnames())
        if unknown:
            raise ValueError(
                "Admin password mapping contains hosts absent from the vault inventory"
            )

    logger.info("Importing %d admin passwords into the vault", len(passwords))
    generator = PasswordGenerator(mode="password", require_special=False)

    for hostname, password in passwords.items():
        if not password:
            logger.warning(
                "Hostname %s has an empty password entry; skipping", hostname
            )
            continue

        template, _ = vault.get_or_create_secret_template(
            name=f"admin@{hostname}",
            owner_type="local",
            secret_type="password",
            vault_dir=vault.dir,
        )
        secret_dir = _secret_directory(template, vault)

        for suffix, value in _admin_secret_values(password, generator):
            secret_name = f"{template.name}_{suffix}"
            secret_file = secret_dir / secret_name
            target_secret_name = secret_name.replace(f"@{hostname}", "")
            target_name = (
                f"SCRT_{template.owner_type}_{template.secret_type}_"
                f"{target_secret_name}"
            )

            existing = next(
                (secret for secret in vault.secrets if secret.name == secret_name),
                None,
            )
            if existing is not None:
                _update_secret(existing, value, vault)
            else:
                Secret.create_secret(value, secret_file, vault)
                timestamp = datetime.now()
                vault.secrets.append(
                    Secret(
                        name=secret_name,
                        template_name=template.name,
                        file=secret_file.as_posix(),
                        target_name=target_name,
                        owner_type=template.owner_type,
                        secret_type=template.secret_type,
                        local_vault_key=template.local_vault_key,
                        created=timestamp,
                        updated=timestamp,
                    )
                )

            if secret_name not in template.secret_names:
                template.secret_names.append(secret_name)
