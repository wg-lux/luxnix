import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Self

from pydantic import BaseModel, field_validator, model_validator

from ...password import PasswordGenerator
from ...password.files import write_private_text
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

    @classmethod
    def generate(cls, name: str, psk_dir: str | Path) -> Self:
        """Generate and persist a new pre-shared key."""
        psk_dir = Path(psk_dir).expanduser().resolve()
        ensure_private_directory(psk_dir)

        psk_file = psk_dir / f"{name}.psk"
        if psk_file.exists():
            warnings.warn(f"PSK file already exists: {psk_file}", stacklevel=2)

        pg = PasswordGenerator(mode="passphrase", num_words=6)
        results = pg.pipe()
        psk = results[0][1]

        write_private_text(psk_file, psk)

        now = datetime.now()
        return cls(name=name, file=str(psk_file), created=now, updated=now)
