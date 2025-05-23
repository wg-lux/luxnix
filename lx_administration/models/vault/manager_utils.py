from pathlib import Path
from datetime import datetime as dt, timedelta as td
from typing import Optional, List, Union, Tuple
import warnings
from lx_administration.logging import get_logger
from .config import OWNER_TYPES, SECRET_TYPES


def _is_valid(validity: td, created: dt, updated: Optional[dt], logger=None) -> bool:
    if not logger:
        logger = get_logger("lx_vault__is_valid")
    assert created, "created is required"

    if not updated:
        updated = created

    is_valid = updated - created <= validity

    return is_valid


def ensure_local_vault_key(path: Union[Path, str], logger=None):
    """Ensure that a local vault key exists, or create it."""
    if not logger:
        logger = get_logger("ensure_local_vault_key")
    if not isinstance(path, Path):
        local_vault_key = Path(path)
    else:
        local_vault_key = path
    if not local_vault_key.exists():
        logger.warning(
            f"Local vault key {local_vault_key} does not exist. Creating new key."
        )
        generate_ansible_key(local_vault_key)


def generate_ansible_key(key_path: Path, mode="password"):
    from ...password import PasswordGenerator
    # Generate a passphrase file, no longer encrypting it with ansible-vault

    assert not key_path.exists(), f"File {key_path} already exists!"

    key_path = key_path.expanduser().resolve()
    pg = PasswordGenerator(mode=mode, n_words=4)
    results = pg.pipe()
    passphrase = results[0][1]

    with open(key_path, "w") as f:
        f.write(passphrase)
    key_path.chmod(0o600)


def generate_secret_dir_path(
    name: str, vault_dir: Path, owner_type: str, secret_type: str
):
    assert owner_type in OWNER_TYPES, f"Invalid owner_type: {owner_type}"
    assert secret_type in SECRET_TYPES, f"Invalid secret_type: {secret_type}"

    vault_dir = Path(vault_dir).expanduser().resolve()
    secret_dir = vault_dir / "secrets" / f"{secret_type}/{owner_type}/{name}"
    secret_dir.mkdir(mode=0o755, parents=True, exist_ok=True)

    return secret_dir


def _get_by_name(obj_list: List, name: str, logger=None):
    if not logger:
        logger = get_logger("lx_vault__get_by_name")
    objs = [obj for obj in obj_list if obj.name == name]
    if not len(objs) <= 1:
        logger.warning(f"Found more than one object: {len(objs)}")
        raise ValueError(f"Found more than one object: {len(objs)}")

    if objs:
        return objs[0]
    else:
        return None


def _get_by_target_name(obj_list: List, target_name: str, logger=None):
    if not logger:
        logger = get_logger("lx_vault__get_by_target_name")
    objs = [obj for obj in obj_list if obj.target_name == target_name]
    if not len(objs) <= 1:
        logger.warning(f"Found more than one object: {len(objs)}")
        raise ValueError(f"Found more than one object: {len(objs)}")

    if objs:
        return objs[0]
    else:
        return None


def _check_unique_list(lst: List[str]) -> bool:
    if not len(lst) == len(set(lst)):
        return False

    return True


def _assert_unique_list(lst: List[str]) -> bool:
    from collections import Counter

    duplicates = [item for item, count in Counter(lst).items() if count > 1]
    if duplicates:
        raise ValueError(f"List contains duplicates: {duplicates}")
    return True
