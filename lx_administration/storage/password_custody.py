"""Private terminal disclosure after authenticated disk-password escrow."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path

from .boot_password import private, secret
from .cutover import atomic_json


class CustodyError(RuntimeError):
    """Operator-safe diagnostic containing no credential values."""


@contextmanager
def terminal():
    # Separate read/write streams: a buffered r+ stream cannot seek on a TTY.
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise CustodyError(
            "Open a private terminal (local console, Konsole or ssh -tt) "
            "and rerun setup; encrypted copies are retained"
        ) from None
    with os.fdopen(fd, "r") as reader:
        if not reader.isatty():
            raise CustodyError("Use a private terminal for password custody")
        with os.fdopen(os.dup(reader.fileno()), "w") as writer:
            yield reader, writer


def ask(host: str, volume: str) -> str:
    # Diagnose a missing terminal before getpass; never fall back to echoed input.
    with terminal():
        return secret(f"Current disk password for {host}/{volume}: ").decode("utf-8")


def acknowledge(primary: Path, record: dict) -> None:
    """Reveal once until acknowledged; bind the receipt to encrypted record bytes."""
    receipt = primary.with_suffix(".acknowledged.json")
    expected = {
        "schema_version": 1,
        "record_sha256": hashlib.sha256(primary.read_bytes()).hexdigest(),
        "machine_id": record["machine_id"],
        "luks_uuid": record["luks_uuid"],
    }
    if receipt.exists() or receipt.is_symlink():
        private(receipt)
        if json.loads(receipt.read_text()) != expected:
            raise CustodyError(
                "Password custody acknowledgement belongs to another record"
            )
        return
    with terminal() as (reader, writer):
        writer.write(
            f"\nVerified vault and independent recovery envelope for "
            f"{record['host']}/{record['volume']}.\n"
            "This password is shown once until acknowledged. "
            "Store it in your password manager.\n"
            "Password (JSON quoted; quotes are not part of it): "
            + json.dumps(record["recovery_passphrase"], ensure_ascii=True)
            + "\nType SAVED to acknowledge secure custody: "
        )
        writer.flush()
        if reader.readline().strip() != "SAVED":
            raise CustodyError(
                "Password custody not acknowledged; encrypted copies retained"
            )
    atomic_json(receipt, expected)
