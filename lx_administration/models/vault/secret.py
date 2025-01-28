from typing import Optional
from pydantic import BaseModel
from datetime import datetime as dt, timedelta as td
from pathlib import Path
import warnings
from lx_administration.logging import get_logger
from lx_administration.utils.paths import str2path
from .manager_utils import _is_valid, _get_by_name


class Secret(BaseModel):
    """
    Stores an individual encrypted secret and references its AccessKey.
    """

    name: str
    file: str
    owner_type: str
    template_name: str
    secret_type: str = "password"
    local_vault_key: Optional[str] = "~/.lxv.key"
    target_name: str
    created: Optional[dt] = None
    updated: Optional[dt] = None
    validity: Optional[td] = td(days=180)

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def create_secret(
        cls,
        secret: str,
        file: str,
        vault: "Vault",  # noqa: F821
    ):
        import subprocess
        from lx_administration.models import Vault

        _vault: Vault = vault

        file_path = Path(file).expanduser().resolve()
        with open(file_path, "w") as f:
            f.write(secret)

        vault_id = _vault.get_local_vault_id()
        assert vault_id, "Vault ID not found for local hostname"

        encrypt_args = [
            "ansible-vault",
            "encrypt",
            f"--encrypt-vault-id={vault_id}",
            file_path.as_posix(),
        ]

        subprocess.run(
            encrypt_args,
            check=True,
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

    def create_re_encrypted_file(
        self,
        target_file: str,
        pre_shared_key_file: str,
        vault: "Vault",  # noqa: F821
    ):
        """Create a copy of the encrypted file with a new key."""
        import subprocess
        import shutil
        import warnings

        source_path = Path(self.file).expanduser().resolve()
        target_path = Path(target_file).expanduser().resolve()
        pre_shared_key_path = Path(pre_shared_key_file).expanduser().resolve()

        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        if not pre_shared_key_path.exists():
            raise FileNotFoundError(f"PSK file not found: {pre_shared_key_path}")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            warnings.warn(f"Target file {target_path} exists and will be overwritten")

        # Copy the source file to target location
        shutil.copy2(source_path, target_path)

        vault_id = vault.get_local_vault_id() if vault else None

        try:
            rekey_args = [
                "ansible-vault",
                "rekey",
                "--new-vault-password-file",
                pre_shared_key_path.as_posix(),
                target_path.as_posix(),
            ]
            if vault_id:
                rekey_args.insert(2, f"--new-vault-id={vault_id}")

            result = subprocess.run(
                rekey_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True,
            )
            if result.stderr:
                warnings.warn(f"Rekey warning: {result.stderr}")

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to rekey file: {e.stderr}")

    def validate(self):
        logger = get_logger("Secret-validate")
        _validity_status = _is_valid(self.validity, self.created, self.updated, logger)

        directory = str2path(self.file, expanduser=True, resolve=True)
        if not directory.exists():
            directory.mkdir(mode=755, parents=True, exist_ok=True)
