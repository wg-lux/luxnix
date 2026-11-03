import os
import tempfile
import warnings
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ansible.errors import AnsibleError
from ansible.parsing.vault import VaultLib, VaultSecret
from pydantic import BaseModel, ConfigDict
from passlib.hash import sha512_crypt

from ...permissions import PRIVATE_FILE_MODE, ensure_private_directory
from ...secret_storage import encrypted_storage
from .manager_utils import _get_by_name

if TYPE_CHECKING:
    from .manager import Vault


def _absolute_path(path: str | Path) -> Path:
    """Expand a path without resolving and following its final symlink."""
    return Path(path).expanduser().absolute()


MASTER_VAULT_ID = "luxnix-master"


def _read_key(path: str | Path) -> VaultSecret:
    """Read a private, nonempty key; never discover identities from Ansible config."""
    key_path = _absolute_path(path)
    if key_path.is_symlink() or not key_path.is_file():
        raise ValueError("Vault key must be an existing regular, non-symlink file")
    if key_path.stat().st_mode & 0o077:
        raise ValueError("Vault key must not grant group or other permissions")
    encrypted_storage(key_path, allow_runtime=True)
    key = key_path.read_bytes().strip()
    if not key:
        raise ValueError("Vault key must not be empty")
    return VaultSecret(key)


def decrypt_secret(
    file: str | Path, key: str | Path, vault_id: str = MASTER_VAULT_ID
) -> bytes:
    """Decrypt with exactly the declared key and identity, without CLI defaults."""
    source = _absolute_path(file)
    if source.is_symlink() or not source.is_file():
        raise FileNotFoundError("Secret must be an existing regular, non-symlink file")
    data = source.read_bytes()
    header = data.split(b"\n", 1)[0]
    # Labels are a format boundary, not cryptographic authentication. VaultLib
    # verifies the ciphertext using the one explicitly supplied key below.
    expected = f"$ANSIBLE_VAULT;1.2;AES256;{vault_id}".encode()
    legacy_default = vault_id == "default" and header == b"$ANSIBLE_VAULT;1.1;AES256"
    if header != expected and not legacy_default:
        raise ValueError(
            "Unexpected vault identity; explicit legacy migration required"
        )
    secret = _read_key(key)
    try:
        return VaultLib([(vault_id, secret)]).decrypt(data)
    except AnsibleError:
        raise ValueError(
            "Secret decryption failed with the declared vault key"
        ) from None


def _encrypt_bytes(value: bytes, key: str | Path, vault_id: str) -> bytes:
    secret = _read_key(key)
    try:
        return VaultLib([(vault_id, secret)]).encrypt(
            value, secret=secret, vault_id=vault_id
        )
    except AnsibleError:
        raise ValueError(
            "Secret encryption failed with the declared vault key"
        ) from None


def _publish_ciphertext(
    data: bytes, target: Path, *, replace: bool = True
) -> tuple[int, int]:
    """Publish only encrypted bytes; migration uses an exclusive new destination."""
    ensure_private_directory(target.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}."
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        identity = os.fstat(descriptor)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
        return identity.st_dev, identity.st_ino
    finally:
        temporary.unlink(missing_ok=True)


def _create_secret_files(values: list[tuple[Path, str]], key: str | Path) -> None:
    """Publish a fresh pair exclusively; roll back owned files on error."""
    encrypted = [
        (path, _encrypt_bytes(value.encode("utf-8"), key, MASTER_VAULT_ID))
        for path, value in values
    ]
    published: list[tuple[Path, tuple[int, int]]] = []
    try:
        for path, data in encrypted:
            identity = _publish_ciphertext(data, path, replace=False)
            published.append((path, identity))
    except BaseException:
        for path, identity in reversed(published):
            try:
                current = path.lstat()
            except FileNotFoundError:
                continue
            if (current.st_dev, current.st_ino) == identity:
                path.unlink()
        raise


def _encrypt_value_atomically(value: str, target: Path, key: str | Path) -> None:
    """Validate old ciphertext before replacing it using the explicit master key."""
    if target.exists() or target.is_symlink():
        decrypt_secret(target, key)
    encrypted = _encrypt_bytes(value.encode("utf-8"), key, MASTER_VAULT_ID)
    _publish_ciphertext(encrypted, target)


def validate_password_pairs(secrets, key, vault_id=MASTER_VAULT_ID) -> None:
    """Reject incomplete or mixed generated credentials before validation/export."""
    pairs = {}
    for secret in secrets:
        if secret.secret_type not in {"password", "system_password"}:
            continue
        suffix = next(
            (s for s in ("_password_hash", "_password") if secret.name.endswith(s)),
            None,
        )
        if suffix is None:
            continue  # Individually imported application secrets are not pairs.
        identity = (
            secret.name.removesuffix(suffix),
            secret.owner_type,
            secret.secret_type,
            secret.template_name,
        )
        pair = pairs.setdefault(identity, {})
        if suffix in pair:
            raise ValueError("Duplicate credential pair metadata")
        pair[suffix] = secret
    for pair in pairs.values():
        if set(pair) != {"_password", "_password_hash"}:
            raise ValueError("Incomplete credential pair; recovery required")
        password = decrypt_secret(pair["_password"].file, key, vault_id)
        encoded = decrypt_secret(pair["_password_hash"].file, key, vault_id)
        try:
            matches = sha512_crypt.verify(password, encoded.decode("utf-8"))
        except (ValueError, UnicodeError):
            matches = False
        if not matches:
            raise ValueError("Credential pair does not match; recovery required")


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
    value: str | None = None

    @staticmethod
    def create_secret(
        secret: str,
        file: str | Path,
        vault: "Vault",
    ) -> str:
        """Create an encrypted secret without exposing a partial target file."""
        _encrypt_value_atomically(secret, _absolute_path(file), vault.key)
        return secret

    @staticmethod
    def check_exists(name: str, file: str | Path, vault: "Vault") -> bool:
        """Distinguish wholly absent state from inconsistent persisted material."""
        target = _absolute_path(file)
        metadata = _get_by_name(vault.secrets, name)
        file_exists = target.exists() or target.is_symlink()
        if file_exists != (metadata is not None):
            raise ValueError(
                f"Secret file/metadata mismatch for {name}; recovery required"
            )
        if target.resolve() != target:
            raise ValueError(f"Secret path contains symlinks for {name}")
        aliases = [
            item
            for item in vault.secrets
            if _absolute_path(item.file).resolve() == target and item.name != name
        ]
        if aliases:
            raise ValueError(f"Conflicting secret path for {name}")
        if metadata is None:
            return False
        if _absolute_path(metadata.file) != target or not target.is_file():
            raise ValueError(f"Conflicting secret file for {name}; recovery required")
        return True

    def create_re_encrypted_file(
        self,
        target_file: str | Path,
        pre_shared_key_file: str | Path,
        vault: "Vault",
    ) -> Path:
        """Atomically create a private client-encrypted copy of this secret."""
        vault.validate_credential_pairs()
        target_path = _absolute_path(target_file)
        plaintext = decrypt_secret(self.file, vault.key)
        key_path = _absolute_path(pre_shared_key_file)
        identities = [
            psk.vault_id_prefix
            for psk in vault.pre_shared_keys
            if _absolute_path(psk.file) == key_path
        ]
        if len(identities) != 1 or not identities[0]:
            raise ValueError("Export PSK must have exactly one registered identity")
        if identities[0] == MASTER_VAULT_ID:
            raise ValueError(
                "Host export identity must differ from the master identity"
            )
        encrypted = _encrypt_bytes(plaintext, key_path, identities[0])
        if target_path.exists():
            warnings.warn(
                f"Target file {target_path} exists and will be overwritten",
                stacklevel=2,
            )
        _publish_ciphertext(encrypted, target_path)
        return target_path

    def update_file_encryption(self, vault: "Vault") -> None:
        """Atomically replace the encrypted file with the current value."""
        if self.value is None:
            raise ValueError(f"Secret.value is not set for {self.name}")
        _encrypt_value_atomically(self.value, _absolute_path(self.file), vault.key)

    def validate_secret(self, *, now: datetime | None = None) -> None:
        """Validate timestamps and require an existing encrypted secret file."""
        if self.created is None:
            raise ValueError(f"Secret.created is not set for {self.name}")

        secret_file = Path(self.file).expanduser().resolve()
        if not secret_file.is_file():
            raise FileNotFoundError(f"Encrypted secret file not found: {secret_file}")
