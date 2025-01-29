from typing import Optional, List, Union
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime as dt
from .config import OWNER_TYPES, SECRET_TYPES
from ...password import PasswordGenerator
from .manager_utils import (
    generate_secret_dir_path,
)
from .secret import Secret
from lx_administration.logging import get_logger


class SecretTemplate(BaseModel):
    """
    Template for generating multiple secrets of the same type/owner.
    """

    name: str
    owner_type: str
    secret_type: str = "password"
    directory: Optional[str] = None
    secret_names: List[str] = []
    generator: Optional[Union[PasswordGenerator]] = None
    local_vault_key: Optional[str] = "~/.lxv.key"

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def create_secret_template(
        cls,
        name: str,
        owner_type: str,
        secret_type: Optional[str] = "password",
        vault_dir: str = "~/.lxv/",
    ):
        template = cls(name=name, owner_type=owner_type, secret_type=secret_type)

        if not template.directory:
            template.directory = template.get_secret_dir(Path(vault_dir)).as_posix()

        if not template.generator:
            template.generator = template.get_secret_generator()

        return template

    def get_secret_generator(self):
        """
        Retrieve a configured secret generator based on the secret_type.

        Returns:
            PasswordGenerator: An instance of PasswordGenerator if secret_type is "password".
        """
        assert (
            self.secret_type in SECRET_TYPES
        ), f"Invalid secret_type: {self.secret_type}"
        if self.secret_type == "password":
            return PasswordGenerator(mode="passphrase", n_words=4)
        if self.secret_type == "system_password":
            return PasswordGenerator(mode="password", key_length=32)

    def validate(self):
        """
        Validate the template's owner_type, secret_type, and directory existence.

        Raises:
            AssertionError: If owner_type or secret_type is invalid or directory does not exist.
        """
        assert self.owner_type in OWNER_TYPES, f"Invalid owner_type: {self.owner_type}"
        assert (
            self.secret_type in SECRET_TYPES
        ), f"Invalid secret_type: {self.secret_type}"

        assert Path(
            self.directory
        ).exists(), f"Directory {self.directory} does not exist!"

    def get_secret_dir(self, vault_dir: Path):
        """
        Generate and return the secret directory path.

        Args:
            vault_dir (Path): Base path to the vault directory.

        Returns:
            Path: The generated secret directory path.
        """
        secret_dir = generate_secret_dir_path(
            self.name,
            vault_dir.expanduser().resolve(),
            self.owner_type,
            self.secret_type,
        )
        return secret_dir

    def create_or_update_secrets(self, vault: "Vault", logger=None):  # noqa: F821
        """
        Create or update secrets within the specified vault using the stored generator.

        Args:
            vault (Vault): The vault object where secrets are stored or updated.

        Returns:
            bool: True if secrets were created or updated, False otherwise.
        """
        from .manager import Vault

        _vault: Vault = vault
        if not logger:
            logger = get_logger("lx_vault__create_or_update_secrets")
        if not self.generator:
            raise ValueError(f"SecretTemplate.generator is not set for {self.name}")

        hostnames = [host.hostname for host in _vault.inventory.all]

        results = self.generator.pipe()
        secret_dir = Path(self.directory).expanduser().resolve()

        self.secret_names = [f"{self.name}_{suffix}" for suffix, secret in results]
        _secrets = [secret for suffix, secret in results]

        for i, secret_name in enumerate(self.secret_names):
            _secret = _secrets[i]
            secret_file = secret_dir / secret_name

            _exists = Secret.check_exists(secret_name, secret_file, _vault)

            if not _exists:
                # Create the encrypted secret file
                Secret.create_secret(
                    secret=_secret,
                    file=str(secret_file),
                    vault=_vault,
                )

                # Create and store the Secret object

                # Some secret names the hostnames which should not be present
                # in the secret_target variable
                pseudo_secret_name = secret_name
                for hostname in hostnames:
                    rm_str = f"@{hostname}"
                    pseudo_secret_name = pseudo_secret_name.replace(rm_str, "")

                if pseudo_secret_name != secret_name:
                    logger.info(
                        f"Replaced occuring hostname in secret_target:\
                             {pseudo_secret_name} != {secret_name}"
                    )
                secret_target = (
                    f"SCRT_{self.owner_type}_{self.secret_type}_{pseudo_secret_name}"
                )

                secret = Secret(
                    name=secret_name,
                    template_name=self.name,
                    file=str(secret_file),
                    target_name=secret_target,
                    owner_type=self.owner_type,
                    secret_type=self.secret_type,
                    local_vault_key=self.local_vault_key,
                    created=dt.now(),
                    updated=dt.now(),
                )
                vault.secrets.append(secret)

        return True
