from typing import Optional, Tuple
from pydantic import BaseModel
from datetime import datetime as dt, timedelta as td
from pathlib import Path
from lx_administration.logging import get_logger
from .config import OWNER_TYPES, SECRET_TYPES
from .manager_utils import (
    _is_valid,
    ensure_local_vault_key,
    generate_ansible_key,
    generate_access_key_path,
)


class AccessKey(BaseModel):
    """
    Represents an encrypted Ansible vault key with metadata.
    """

    name: str
    description: Optional[str] = ""
    vault_dir: str
    file: str
    local_vault_key: str = "~/.lxv.key"
    created: Optional[dt] = None
    updated: Optional[dt] = None
    validity: Optional[td] = td(days=180)
    owner_type: Optional[str] = "roles"

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def get_or_create(
        cls,
        name: str,
        owner_type: str,
        secret_type: str,
        local_vault_key: str,
        vault_dir="~/.lxv/",
        logger=None,
    ) -> Tuple["AccessKey", bool]:
        vault_dir_path = Path(vault_dir).expanduser().resolve()
        if not vault_dir_path.exists():
            vault_dir_path.mkdir(parents=True)

        if not logger:
            logger = get_logger("AccessKey-get_or_create")

        created = dt.now()
        updated = dt.now()
        is_new = False

        access_key_file = generate_access_key_path(
            name, vault_dir_path, owner_type, secret_type=secret_type
        )
        ensure_local_vault_key(local_vault_key, logger)
        local_vault_key_path = Path(local_vault_key).expanduser().resolve()
        print(f"Access Key File: {access_key_file}")
        if not access_key_file.exists():
            is_new = True
            generate_ansible_key(access_key_file, local_vault_key_path)

        key = cls(
            name=name,
            file=access_key_file.as_posix(),
            vault_dir=vault_dir_path.as_posix(),
            local_vault_key=local_vault_key,
            created=created,
            updated=updated,
        )

        key.validate()

        return key, is_new

    def validate(self):
        """
        Validates the access key by checking validity window and owner type.
        """
        logger = get_logger("AccessKey-validate")
        _validity_status = _is_valid(self.validity, self.created, self.updated, logger)
        assert self.owner_type in OWNER_TYPES, f"Invalid owner_type: {self.owner_type}"
