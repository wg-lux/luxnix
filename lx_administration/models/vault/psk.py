import os
import re
import stat
from datetime import datetime, timedelta
from pathlib import Path
from typing import Self

from pydantic import BaseModel, field_validator, model_validator

from ...password import PasswordGenerator
from ...secret_storage import encrypted_storage
from ...utils.file_operations import atomic_create_file
from ...permissions import ensure_private_directory

DEFAULT_VALIDITY = timedelta(days=30)


class PreSharedKey(BaseModel):
    """Pre-shared key used to distribute secrets to one client."""

    name: str
    file: str
    created: datetime | None = None
    updated: datetime | None = None
    validity: timedelta | None = DEFAULT_VALIDITY
    vault_id_prefix: str | None = None

    @field_validator("file", mode="before")
    @classmethod
    def serialize_file_path(cls, value: object) -> object:
        return str(value) if isinstance(value, Path) else value

    @field_validator("created", "updated", mode="before")
    @classmethod
    def parse_timestamp(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return value

    @field_validator("validity", mode="before")
    @classmethod
    def parse_validity(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        try:
            if value.startswith("P") and value.endswith("D"):
                days = int(value[1:-1])
            else:
                days = int(value.split()[0])
            return timedelta(days=days)
        except (ValueError, IndexError):
            return DEFAULT_VALIDITY

    @model_validator(mode="after")
    def normalize_vault_id_prefix(self) -> Self:
        prefix = self.vault_id_prefix or self.name
        self.vault_id_prefix = prefix.replace("@", "--")
        return self

    def get_vid(self) -> str:
        return f"{self.vault_id_prefix}@{self.file}"

    @property
    def file_path(self) -> Path:
        """Return the expanded absolute PSK path."""
        return Path(self.file).expanduser().resolve()

    def validate_file(self) -> None:
        """Require a usable existing key without reading or replacing its bytes."""
        path = Path(self.file).expanduser().absolute()
        if path.resolve() != path:
            raise ValueError("PSK path may not contain symlinks")
        encrypted_storage(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_size == 0):
                raise ValueError("PSK must be a nonempty owned private regular file")
        finally:
            os.close(fd)

    @classmethod
    def generate(cls, name: str, psk_dir: str | Path) -> Self:
        """Generate and persist a new pre-shared key."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", name):
            raise ValueError("Invalid PSK name")
        psk_dir = Path(psk_dir).expanduser().absolute()
        if psk_dir.resolve() != psk_dir:
            raise ValueError("PSK directory may not contain symlinks")
        ensure_private_directory(psk_dir)

        psk_file = psk_dir / f"{name}.psk"
        if psk_file.exists() or psk_file.is_symlink():
            raise FileExistsError(
                "PSK already exists; recover metadata or rotate explicitly"
            )

        pg = PasswordGenerator(mode="passphrase", num_words=6)
        psk = pg.generate_random_passphrase()
        encrypted_storage(psk_file)
        atomic_create_file(
            destination=psk_file, content=[psk.encode("utf-8")], file_mode=0o600
        )

        now = datetime.now()
        return cls(name=name, file=str(psk_file), created=now, updated=now)
