from typing import Optional
from pydantic import BaseModel
from datetime import datetime as dt, timedelta as td
from pathlib import Path
import warnings
from lx_administration.logging import get_logger
from lx_administration.utils.paths import str2path
from .manager_utils import _is_valid, _get_by_name
from .access_key import AccessKey


class Secret(BaseModel):
    """
    Stores an individual encrypted secret and references its AccessKey.
    """

    name: str
    file: str
    access_key: AccessKey
    owner_type: str
    secret_type: str = "password"
    local_vault_key: Optional[str] = "~/.lxv.key"
    created: Optional[dt] = None
    updated: Optional[dt] = None
    validity: Optional[td] = td(days=180)

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def create_secret(cls, secret: str, file: str, access_key: AccessKey):
        import subprocess

        access_key_path = Path(access_key.file).expanduser().resolve().as_posix()
        file_path = Path(file).expanduser().resolve()
        with open(file_path, "w") as f:
            f.write(secret)

        # use ansible-vault to encrypt the file using the access_key
        subprocess.run(
            [
                "ansible-vault",
                "encrypt",
                "--vault-password-file",
                access_key_path,
                file_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return secret

    @classmethod
    def check_exists(cls, name: str, file: str, vault: "Vault"):  # noqa: F821
        fp = Path(file)
        if not fp.exists() and not _get_by_name(vault.secrets, name):
            return False

        elif fp.exists() and _get_by_name(vault.secrets, name):
            return True

        else:
            warnings.warn(f"Secret.check_exists(): exists: {fp.exists()}, ")
            warnings.warn(
                f"File {file} exists but secret {name} does not exist in vault or vice versa"
            )

    def get_or_create_access_key(self, vault_dir: str):
        access_key = AccessKey.get_or_create(
            name=self.name,
            owner_type=self.owner_type,
            vault_dir=vault_dir,
            local_vault_key=self.local_vault_key,
        )

        return access_key

    def generate_deployment_secrets():
        pass

    def validate(self):
        logger = get_logger("Secret-validate")
        _validity_status = _is_valid(self.validity, self.created, self.updated, logger)

        directory = str2path(self.file, expanduser=True, resolve=True)
        if not directory.exists():
            directory.mkdir(mode=755, parents=True, exist_ok=True)
