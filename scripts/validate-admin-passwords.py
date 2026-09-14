#!/usr/bin/env python3
"""Verify admin passwords stored in the Luxnix vault against a source file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lx_administration.logging import get_logger
from lx_administration.models.vault import Vault, load_admin_passwords
from lx_administration.password import PasswordGenerator
from lx_administration.models.vault.secret import MASTER_VAULT_ID, decrypt_secret

LOGGER = get_logger("validate-admin-passwords", reset=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate admin passwords stored in the Luxnix vault"
    )
    parser.add_argument(
        "--vault-dir",
        default="~/.lxv",
        help="Vault directory (where secrets and PSKs are stored)",
    )
    parser.add_argument(
        "--vault-key",
        default="~/.lxv.key",
        help="Path to the local vault key used to encrypt secrets",
    )
    parser.add_argument(
        "--admin-passwords",
        default="ansible/secrets/admin-passwords.yml",
        help="YAML file containing admin passwords under 'admin_passwords'",
    )
    parser.add_argument(
        "--vault-id",
        default=MASTER_VAULT_ID,
        choices=[MASTER_VAULT_ID],
        help="Explicit master identity; migrate legacy ciphertext before validation.",
    )
    return parser.parse_args()


def _secret_paths(vault_dir: Path, hostname: str) -> tuple[Path, Path]:
    base = vault_dir / "secrets" / "password" / "local" / f"admin@{hostname}"
    password_file = base / f"admin@{hostname}_password"
    hash_file = base / f"admin@{hostname}_password_hash"
    return password_file, hash_file


def _decrypt_secret(file_path: Path, vault_id: str, key_path: Path) -> str:
    try:
        return decrypt_secret(file_path, key_path, vault_id).decode("utf-8")
    except ValueError:
        raise RuntimeError(
            "Failed to decrypt secret with the declared master key"
        ) from None


def main() -> None:
    args = _parse_args()

    vault_dir = Path(args.vault_dir).expanduser().resolve()
    vault_key = Path(args.vault_key).expanduser().absolute()
    admin_file = Path(args.admin_passwords).expanduser().absolute()

    vault = Vault.load_dir(vault_dir.as_posix(), vault_key.as_posix())
    vault.dir = vault_dir.as_posix()
    vault.key = vault_key.as_posix()

    vault_id = args.vault_id

    LOGGER.info("Using vault id '%s' with key %s", vault_id, vault_key)

    passwords = load_admin_passwords(admin_file, strict=True)
    if not passwords:
        LOGGER.warning("No admin passwords found in %s", admin_file)
        sys.exit(0)

    mismatches: list[str] = []
    missing: list[str] = []
    generator = PasswordGenerator(mode="password", require_special=False)

    for hostname, password in passwords.items():
        password_file, hash_file = _secret_paths(vault_dir, hostname)
        try:
            stored_password = _decrypt_secret(password_file, vault_id, vault_key)
        except FileNotFoundError:
            missing.append(f"{hostname}: missing password secret {password_file}")
            continue
        except RuntimeError as exc:
            mismatches.append(f"{hostname}: {exc}")
            continue

        if stored_password != password:
            mismatches.append(f"{hostname}: plaintext password mismatch")

        try:
            stored_hash = _decrypt_secret(hash_file, vault_id, vault_key)
        except FileNotFoundError:
            missing.append(f"{hostname}: missing password hash secret {hash_file}")
            continue
        except RuntimeError as exc:
            mismatches.append(f"{hostname}: {exc}")
            continue

        if not generator.verify_password_hash(password, stored_hash):
            mismatches.append(f"{hostname}: password hash mismatch")

    if missing or mismatches:
        for msg in missing:
            LOGGER.error(msg)
        for msg in mismatches:
            LOGGER.error(msg)
        LOGGER.error(
            "Validation failed: %d missing secrets, %d mismatches",
            len(missing),
            len(mismatches),
        )
        sys.exit(1)

    LOGGER.info("All %d admin passwords match the vault entries", len(passwords))


if __name__ == "__main__":
    main()
