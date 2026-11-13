import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, ConfigDict, Field

from lx_administration.logging import get_logger

from ...password import PasswordGenerator
from .config import OWNER_TYPES, SECRET_TYPES
from .manager_utils import generate_secret_dir_path
from .secret import Secret, _create_secret_files, validate_password_pairs

if TYPE_CHECKING:
    from .manager import Vault


class SecretTemplate(BaseModel):
    """Template for generating secrets of one owner and type."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    owner_type: str
    secret_type: str = "password"
    directory: str | None = None
    secret_names: list[str] = Field(default_factory=list)
    generator: PasswordGenerator | None = None
    local_vault_key: str | None = "~/.lxv.key"

    @classmethod
    def create_secret_template(
        cls,
        name: str,
        owner_type: str,
        secret_type: str = "password",
        vault_dir: str | Path = "~/.lxv/",
    ) -> Self:
        template = cls(name=name, owner_type=owner_type, secret_type=secret_type)
        template.generator = template.get_secret_generator()
        template.directory = template.get_secret_dir(Path(vault_dir)).as_posix()

        return template

    def get_secret_generator(self) -> PasswordGenerator:
        """Return the generator configured for this secret type."""
        if self.secret_type not in SECRET_TYPES:
            raise ValueError(f"Invalid secret_type: {self.secret_type}")
        if self.secret_type not in {"password", "system_password"}:
            raise ValueError(f"Unsupported generated secret type: {self.secret_type}")
        if self.secret_type == "password":
            return PasswordGenerator(mode="passphrase", num_words=4)
        return PasswordGenerator(mode="password", key_length=32)

    def assert_valid(self) -> None:
        """Validate the owner, secret type, and output directory."""
        if self.owner_type not in OWNER_TYPES:
            raise ValueError(f"Invalid owner_type: {self.owner_type}")
        if self.secret_type not in SECRET_TYPES:
            raise ValueError(f"Invalid secret_type: {self.secret_type}")
        if self.directory is None:
            raise ValueError("directory must be set on SecretTemplate")
        if not Path(self.directory).is_dir():
            raise ValueError(f"Directory {self.directory} does not exist")

    def get_secret_dir(self, vault_dir: str | Path) -> Path:
        """Create and return this template's secret directory."""
        return generate_secret_dir_path(
            self.name,
            Path(vault_dir).expanduser().resolve(),
            self.owner_type,
            self.secret_type,
        )

    def _secret_paths(self, vault: "Vault") -> list[Path]:
        if Path(self.name).name != self.name or self.name in (".", ".."):
            raise ValueError("Secret template name must be a single path component")
        directory = (
            self.get_secret_dir(Path(vault.dir))
            if self.directory is None
            else Path(self.directory).expanduser().absolute()
        )
        return [
            directory / f"{self.name}_{suffix}"
            for suffix in ("password", "password_hash")
        ]

    def _target_name(self, name: str, vault: "Vault") -> str:
        for host in vault._require_inventory().all:
            if host.hostname:
                name = name.replace(f"@{host.hostname}", "")
        return f"SCRT_{self.owner_type}_{self.secret_type}_{name}"

    def check_persisted_state(self, vault: "Vault") -> bool:
        """Admit only a wholly absent pair or a complete, matching encrypted pair."""
        self.get_secret_generator()  # Never accept password material as a key/cert.
        paths = self._secret_paths(vault)
        names = [path.name for path in paths]
        present = [Secret.check_exists(path.name, path, vault) for path in paths]
        related = [item for item in vault.secrets if item.template_name == self.name]
        if any(item.name not in names for item in related):
            raise ValueError(f"Conflicting secret metadata for {self.name}")
        if any(present) != all(present):
            raise ValueError(
                f"Incomplete credential pair for {self.name}; recovery required"
            )
        if self.secret_names != (names if any(present) else []):
            raise ValueError(
                f"Conflicting secret_names for {self.name}; recovery required"
            )
        for item in vault.secrets:
            if item.name not in names:
                continue
            if (
                item.template_name != self.name
                or item.target_name != self._target_name(item.name, vault)
                or item.owner_type != self.owner_type
                or item.secret_type != self.secret_type
                or item.local_vault_key != self.local_vault_key
            ):
                raise ValueError(f"Conflicting secret metadata for {self.name}")
        if not any(present):
            return False
        validate_password_pairs(related, vault.key)
        return True

    def create_or_update_secrets(
        self,
        vault: "Vault",
        logger: logging.Logger | None = None,
    ) -> bool:
        """Create a new pair; inconsistent material requires explicit recovery."""
        logger = logger or get_logger("lx_vault__create_or_update_secrets")
        if self.generator is None:
            raise ValueError(f"SecretTemplate.generator is not set for {self.name}")
        vault._require_inventory()
        if self.check_persisted_state(vault):
            return False
        paths = self._secret_paths(vault)
        results = self.generator.pipe()
        if [suffix for suffix, _ in results] != ["password", "password_hash"]:
            raise ValueError("Generator must return a complete password/hash pair")
        timestamp = datetime.now()
        metadata = []
        for path in paths:
            metadata.append(
                Secret(
                    name=path.name,
                    template_name=self.name,
                    file=str(path),
                    target_name=self._target_name(path.name, vault),
                    owner_type=self.owner_type,
                    secret_type=self.secret_type,
                    local_vault_key=self.local_vault_key,
                    created=timestamp,
                    updated=timestamp,
                )
            )
        _create_secret_files(
            [(path, value) for path, (_, value) in zip(paths, results, strict=True)],
            vault.key,
        )
        vault.secrets.extend(metadata)
        self.secret_names = [path.name for path in paths]
        logger.info("Created credential pair for template %s", self.name)
        return True
