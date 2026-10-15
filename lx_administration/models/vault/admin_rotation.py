"""Validate an admin rotation and obtain explicit local terminal consent."""

import os
import re

from passlib.hash import sha512_crypt


def verify(payload: dict[str, str]) -> str:
    password = payload["password"]
    replacement_hash = payload["replacement_hash"].strip()
    current_hash = payload["current_hash"].strip()
    if not password or not sha512_crypt.identify(replacement_hash):
        raise ValueError("Invalid replacement password/hash format")
    if not sha512_crypt.verify(password, replacement_hash):
        raise ValueError("Replacement password/hash mismatch")
    if current_hash == replacement_hash:
        return "already_current"
    # Unknown live formats cannot establish old-password rejection. Support
    # locked accounts explicitly; require a separate migration for other hashes.
    if current_hash not in ("!", "*", "!!"):
        if not sha512_crypt.identify(current_hash):
            raise ValueError(
                "Unsupported current hash; use the account recovery procedure"
            )
        if sha512_crypt.verify(password, current_hash):
            raise ValueError("Replacement reuses the current password")
    return "replacement"


def confirm_on_terminal(host: str, payload: dict[str, str]) -> bool:
    """Display once per invocation, outside stdout/stderr and Ansible callbacks."""
    verify(payload)
    password = payload["password"]
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", host):
        raise ValueError("Invalid rotation host")
    if not all(character.isprintable() for character in password):
        raise ValueError("Password contains unsafe terminal control characters")
    # A pipe or CI run cannot supply consent. No echoed-input fallback.
    terminal_path = os.environ.get("LUXNIX_ROTATION_TTY", "/dev/tty")
    if not terminal_path.startswith("/dev/"):
        raise ValueError("Terminal device required")
    descriptor = os.open(terminal_path, os.O_RDWR | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "r") as reader:
        if not reader.isatty():
            raise ValueError("Interactive terminal required")
        return _ask(reader, password, host)


def _ask(reader, password: str, host: str) -> bool:
    with os.fdopen(os.dup(reader.fileno()), "w") as terminal:
        terminal.write(
            "\nThis password will only be shown once during this run. "
            "Store it in a safe place.\n"
            f"Machine: {host}\nNew admin password: {password}\n"
        )
        while True:
            terminal.write(f"Activate new admin password for machine {host}? [y/n]: ")
            terminal.flush()
            answer = reader.readline()
            if not answer:
                return False
            answer = answer.strip()
            if answer == "y":
                return True
            if answer in ("n", ""):
                return False
            terminal.write("Please answer y or n.\n")
