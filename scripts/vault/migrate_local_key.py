#!/usr/bin/env python3
"""Explicitly re-encrypt one legacy ciphertext into a new, verified master copy.

Run only after a custodian reviews the source/key mapping and encrypted backup.
This helper never replaces the original, modifies metadata, deletes keys, or
publishes exports. Use a separate destination for every file, then review all
copies and the vault metadata path mapping before switching the vault as a unit.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from lx_administration.models.vault.secret import (
    MASTER_VAULT_ID,
    _absolute_path,
    _encrypt_bytes,
    _publish_ciphertext,
    decrypt_secret,
)


def migrate_file(
    source: Path,
    output: Path,
    legacy_key: Path,
    legacy_id: str,
    master_key: Path,
) -> None:
    """Preserve the original ciphertext and keys, and refuse existing output."""
    output = _absolute_path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("Migration output already exists; refusing replacement")
    plaintext = decrypt_secret(source, legacy_key, legacy_id)
    encrypted = _encrypt_bytes(plaintext, master_key, MASTER_VAULT_ID)
    # Verify before publication without ever writing plaintext to disk.
    from ansible.parsing.vault import VaultLib

    from lx_administration.models.vault.secret import _read_key

    key = _read_key(master_key)
    if VaultLib([(MASTER_VAULT_ID, key)]).decrypt(encrypted) != plaintext:
        raise ValueError("Migration verification failed")
    _publish_ciphertext(encrypted, output, replace=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--legacy-key", required=True, type=Path)
    parser.add_argument("--legacy-id", required=True)
    parser.add_argument("--master-key", required=True, type=Path)
    parser.add_argument("--confirm-migration", required=True, action="store_true")
    args = parser.parse_args()
    try:
        migrate_file(
            args.source, args.output, args.legacy_key, args.legacy_id, args.master_key
        )
    except (OSError, ValueError):
        parser.exit(
            1,
            "Migration failed; source and keys retained; inspect key/path contract.\n",
        )
    print("Verified encrypted copy created; source, keys, and metadata retained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
