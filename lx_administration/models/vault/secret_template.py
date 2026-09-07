import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, ConfigDict, Field

from lx_administration.logging import get_logger

from ...password import PasswordGenerator
from .config import OWNER_TYPES, SECRET_TYPES
from .manager_utils import generate_secret_dir_path
from .secret import Secret

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
        template.directory = template.get_secret_dir(Path(vault_dir)).as_posix()
        template.generator = template.get_secret_generator()

        return template

    def get_secret_generator(self) -> PasswordGenerator:
        """Return the generator configured for this secret type."""
        if self.secret_type not in SECRET_TYPES:
            raise ValueError(f"Invalid secret_type: {self.secret_type}")
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

    def create_or_update_secrets(
        self,
        vault: "Vault",
        logger: logging.Logger | None = None,
    ) -> bool:
        """Materialize missing secrets and report whether the vault changed."""
        logger = logger or get_logger("lx_vault__create_or_update_secrets")
        if self.generator is None:
            raise ValueError(f"SecretTemplate.generator is not set for {self.name}")

        inventory = vault._require_inventory()
        hostnames = [host.hostname for host in inventory.all if host.hostname]
        results = self.generator.pipe()

        if self.directory is None:
            secret_dir = self.get_secret_dir(Path(vault.dir)).expanduser().resolve()
        else:
            secret_dir = Path(self.directory).expanduser().resolve()

        generated_secrets = [
            (f"{self.name}_{suffix}", secret_value) for suffix, secret_value in results
        ]
        self.secret_names = [name for name, _ in generated_secrets]
        changed = False

        for secret_name, secret_value in generated_secrets:
            secret_file = secret_dir / secret_name
            if Secret.check_exists(secret_name, str(secret_file), vault):
                continue

            Secret.create_secret(
                secret=secret_value,
                file=str(secret_file),
                vault=vault,
            )

            target_secret_name = secret_name
            for hostname in hostnames:
                target_secret_name = target_secret_name.replace(f"@{hostname}", "")

            if target_secret_name != secret_name:
                logger.info(
                    "Removed inventory hostname from secret target: %s -> %s",
                    secret_name,
                    target_secret_name,
                )
            target_name = (
                f"SCRT_{self.owner_type}_{self.secret_type}_{target_secret_name}"
            )
            timestamp = datetime.now()
            vault.secrets.append(
                Secret(
                    name=secret_name,
                    template_name=self.name,
                    file=str(secret_file),
                    target_name=target_name,
                    owner_type=self.owner_type,
                    secret_type=self.secret_type,
                    local_vault_key=self.local_vault_key,
                    created=timestamp,
                    updated=timestamp,
                )
            )
            changed = True

        return changed
