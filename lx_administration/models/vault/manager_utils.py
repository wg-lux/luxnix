import logging
from collections import Counter
from collections.abc import Hashable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from lx_administration.logging import get_logger

from ...password.files import write_private_text
from .config import OWNER_TYPES, SECRET_TYPES


def _is_valid(
    validity: timedelta,
    created: datetime,
    updated: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Return whether a secret is within its validity window."""
    reference_time = updated or created
    current_time = now or datetime.now(tz=reference_time.tzinfo)
    age = current_time - reference_time
    return timedelta(0) <= age <= validity


def ensure_local_vault_key(
    path: Path | str,
    logger: logging.Logger | None = None,
) -> Path:
    """Ensure that a local vault key exists, or create it."""
    logger = logger or get_logger("ensure_local_vault_key")
    local_vault_key = Path(path).expanduser().resolve()
    if not local_vault_key.exists():
        logger.warning(
            "Local vault key %s does not exist; creating it", local_vault_key
        )
        generate_ansible_key(local_vault_key)
    return local_vault_key


def generate_ansible_key(
    key_path: Path | str,
    mode: Literal["password", "passphrase"] = "password",
) -> None:
    """Generate a new local Ansible Vault key."""
    from ...password import PasswordGenerator

    key_path = Path(key_path).expanduser().resolve()
    if key_path.exists():
        raise FileExistsError(f"File {key_path} already exists")

    pg = PasswordGenerator(mode=mode, num_words=4)
    results = pg.pipe()
    passphrase = results[0][1]

    write_private_text(key_path, passphrase)


def generate_secret_dir_path(
    name: str,
    vault_dir: Path | str,
    owner_type: str,
    secret_type: str,
) -> Path:
    """Create and return the directory for one secret template."""
    if owner_type not in OWNER_TYPES:
        raise ValueError(f"Invalid owner_type: {owner_type}")
    if secret_type not in SECRET_TYPES:
        raise ValueError(f"Invalid secret_type: {secret_type}")

    vault_root = Path(vault_dir).expanduser().resolve()
    secret_dir = vault_root / "secrets" / secret_type / owner_type / name
    secret_dir.mkdir(mode=0o755, parents=True, exist_ok=True)

    return secret_dir


def _get_unique_by_attribute[ModelT](
    objects: Sequence[ModelT],
    attribute: str,
    expected: object,
    logger: logging.Logger,
) -> ModelT | None:
    matches = [obj for obj in objects if getattr(obj, attribute) == expected]
    if len(matches) > 1:
        message = (
            f"Found {len(matches)} objects with {attribute}={expected!r}; expected one"
        )
        logger.warning("%s", message)
        raise ValueError(message)
    return matches[0] if matches else None


def _get_by_name[ModelT](
    objects: Sequence[ModelT],
    name: str,
    logger: logging.Logger | None = None,
) -> ModelT | None:
    """Return the only object with the requested name, if present."""
    logger = logger or get_logger("lx_vault__get_by_name")
    return _get_unique_by_attribute(objects, "name", name, logger)


def _get_by_target_name[ModelT](
    objects: Sequence[ModelT],
    target_name: str,
    logger: logging.Logger | None = None,
) -> ModelT | None:
    """Return the only object with the requested target name, if present."""
    logger = logger or get_logger("lx_vault__get_by_target_name")
    return _get_unique_by_attribute(objects, "target_name", target_name, logger)


def _assert_unique_list(values: Sequence[Hashable]) -> None:
    """Raise when a sequence contains duplicate values."""
    duplicates = [item for item, count in Counter(values).items() if count > 1]
    if duplicates:
        raise ValueError(f"List contains duplicates: {duplicates}")
