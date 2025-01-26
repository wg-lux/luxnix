from pathlib import Path
from pydantic import BaseModel, model_validator
from typing import Optional
from datetime import datetime as dt, timedelta as td
from ...password import PasswordGenerator
from .config import yaml
import warnings
from ...logging import get_logger


class PreSharedKey(BaseModel):
    """
    Pre-shared key used for secure distribution of other secrets.
    """

    name: str
    file: str  # Changed from Path to str for YAML serialization
    created: Optional[dt] = None
    updated: Optional[dt] = None
    validity: Optional[td] = td(days=30)  # PSKs are shorter-lived than regular keys

    class Config:
        arbitrary_types_allowed = True

    @model_validator(mode="before")
    @classmethod
    def validate_data(cls, data):
        if isinstance(data, (str, bytes)):
            return data

        if not isinstance(data, dict):
            return data

        # Work with a copy
        data = dict(data)

        # Convert file Path to string
        if isinstance(data.get("file"), Path):
            data["file"] = str(data["file"])

        # Handle datetime fields
        for field in ["created", "updated"]:
            if field in data and isinstance(data[field], str):
                try:
                    data[field] = dt.fromisoformat(data[field].replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    data[field] = None

        # Handle validity duration
        if "validity" in data and isinstance(data["validity"], str):
            try:
                if data["validity"].startswith("P") and data["validity"].endswith("D"):
                    days = int(data["validity"][1:-1])
                else:
                    days = int(data["validity"].split()[0])
                data["validity"] = td(days=days)
            except (ValueError, IndexError):
                data["validity"] = td(days=30)

        return data

    def model_dump(self, **kwargs):
        """Custom serialization for YAML dumping"""
        data = super().model_dump(**kwargs)
        # Convert validity to ISO format
        if "validity" in data and isinstance(data["validity"], td):
            data["validity"] = f"P{data['validity'].days}D"
        return data

    @property
    def file_path(self) -> Path:
        """Get file path as Path object"""
        return Path(self.file).expanduser().resolve()

    @classmethod
    def generate(cls, name: str, psk_dir: Path, logger=None):
        # FIXME
        """Generate a new pre-shared key"""
        if not logger:
            logger = get_logger("lx_vault__generate_psk")
        psk_dir = psk_dir.expanduser().resolve()
        psk_dir.mkdir(parents=True, exist_ok=True)

        psk_file = psk_dir / f"{name}.psk"
        if psk_file.exists():
            warnings.warn(f"PSK file already exists: {psk_file}")

        # Generate PSK using PasswordGenerator
        pg = PasswordGenerator(
            mode="passphrase", n_words=6
        )  # Longer passphrase for PSK
        results = pg.pipe()
        psk = results[0][1]

        # Write PSK to file with tight permissions
        with open(psk_file, "w") as f:
            f.write(psk)
        psk_file.chmod(0o600)

        return cls(name=name, file=str(psk_file), created=dt.now(), updated=dt.now())

    def encrypt_access_key(self, access_key_path: Path, target_path: Path):
        """Encrypt an access key using this PSK"""
        from cryptography.fernet import Fernet
        import base64

        # Derive Fernet key from PSK
        with open(self.file_path, "r") as f:
            psk = f.read().encode()
        key = base64.urlsafe_b64encode(psk[:32].ljust(32, b"\0"))
        f = Fernet(key)

        # Encrypt access key
        with open(access_key_path, "rb") as f_in:
            data = f_in.read()
        encrypted = f.encrypt(data)

        # Write encrypted data
        with open(target_path, "wb") as f_out:
            f_out.write(encrypted)

    def decrypt_access_key(self, encrypted_path: Path, target_path: Path):
        """Decrypt an access key using this PSK"""
        from cryptography.fernet import Fernet
        import base64

        # Derive Fernet key from PSK
        with open(self.file_path, "r") as f:
            psk = f.read().encode()
        key = base64.urlsafe_b64encode(psk[:32].ljust(32, b"\0"))
        f = Fernet(key)

        # Decrypt access key
        with open(encrypted_path, "rb") as f_in:
            encrypted = f_in.read()
        decrypted = f.decrypt(encrypted)

        # Write decrypted data
        with open(target_path, "wb") as f_out:
            f_out.write(decrypted)
