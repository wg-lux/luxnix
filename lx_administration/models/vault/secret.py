import os
import shutil
import subprocess
import tempfile
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from ...permissions import PRIVATE_FILE_MODE, ensure_private_directory
from .manager_utils import _get_by_name, _is_valid

if TYPE_CHECKING:
    from .manager import Vault


DEFAULT_VALIDITY = timedelta(days=180)


def _absolute_path(path: str | Path) -> Path:
    """Expand a path without resolving and following its final symlink."""
    return Path(path).expanduser().absolute()


def _encrypt_value_atomically(value: str, target: Path, vault_id: str) -> None:
    """Encrypt a temporary private file before replacing the target."""
    ensure_private_directory(target.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        text=True,
    )
    temporary = Path(temporary_name)

    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(value)

        subprocess.run(
            [
                "ansible-vault",
                "encrypt",
                f"--encrypt-vault-id={vault_id}",
                temporary.as_posix(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        temporary.chmod(PRIVATE_FILE_MODE)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


class Secret(BaseModel):
    """Metadata and lifecycle operations for an encrypted secret."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    file: str
    owner_type: str
    template_name: str
    secret_type: str = "password"
    local_vault_key: str | None = "~/.lxv.key"
    target_name: str
    created: datetime | None = None
    updated: datetime | None = None
    validity: timedelta | None = DEFAULT_VALIDITY
    value: str | None = None

    @staticmethod
    def create_secret(
        secret: str,
        file: str | Path,
        vault: "Vault",
    ) -> str:
        """Create an encrypted secret without exposing a partial target file."""
        vault_id = vault.get_local_vault_id()
        if not vault_id:
            raise ValueError("Vault ID not found for local hostname")

        _encrypt_value_atomically(secret, _absolute_path(file), vault_id)
        return secret

    @staticmethod
    def check_exists(name: str, file: str | Path, vault: "Vault") -> bool:
        """Return whether both the secret metadata and encrypted file exist."""
        file_exists = Path(file).exists()
        metadata_exists = _get_by_name(vault.secrets, name) is not None
        if file_exists == metadata_exists:
            return file_exists

        warnings.warn(
            f"Secret file/metadata mismatch for {name}: file={file_exists}, "
            f"metadata={metadata_exists}",
            stacklevel=2,
        )
        return False

    def create_re_encrypted_file(
        self,
        target_file: str | Path,
        pre_shared_key_file: str | Path,
        vault: "Vault",
    ) -> Path:
        """Atomically create a private client-encrypted copy of this secret."""
        source_path = Path(self.file).expanduser().resolve()
        target_path = _absolute_path(target_file)
        pre_shared_key_path = Path(pre_shared_key_file).expanduser().resolve()

        if not source_path.is_file():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        if not pre_shared_key_path.is_file():
            raise FileNotFoundError(f"PSK file not found: {pre_shared_key_path}")

        ensure_private_directory(target_path.parent)
        if target_path.exists():
            warnings.warn(
                f"Target file {target_path} exists and will be overwritten",
                stacklevel=2,
            )

        descriptor, temporary_name = tempfile.mkstemp(
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
        )
        os.close(descriptor)
        temporary = Path(temporary_name)

        try:
            shutil.copyfile(source_path, temporary)
            temporary.chmod(PRIVATE_FILE_MODE)
            subprocess.run(
                [
                    "ansible-vault",
                    "rekey",
                    "--new-vault-password-file",
                    pre_shared_key_path.as_posix(),
                    temporary.as_posix(),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            temporary.chmod(PRIVATE_FILE_MODE)
            os.replace(temporary, target_path)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"Failed to rekey secret file (ansible-vault exit {error.returncode})"
            ) from error
        finally:
            temporary.unlink(missing_ok=True)

        return target_path

    def update_file_encryption(self, vault: "Vault") -> None:
        """Atomically replace the encrypted file with the current value."""
        if self.value is None:
            raise ValueError(f"Secret.value is not set for {self.name}")
        vault_id = vault.get_local_vault_id()
        if not vault_id:
            raise ValueError("Vault ID not found for local hostname")

        _encrypt_value_atomically(
            self.value,
            _absolute_path(self.file),
            vault_id,
        )

    def validate_secret(self, *, now: datetime | None = None) -> None:
        """Validate timestamps and require an existing encrypted secret file."""
        if self.created is None:
            raise ValueError(f"Secret.created is not set for {self.name}")

        validity = self.validity or DEFAULT_VALIDITY
        if not _is_valid(validity, self.created, self.updated, now):
            raise ValueError(f"Secret {self.name} is outside its validity window")

        secret_file = Path(self.file).expanduser().resolve()
        if not secret_file.is_file():
            raise FileNotFoundError(f"Encrypted secret file not found: {secret_file}")
