"""
Utilities for handling SSH keys: RSA and Ed25519 generation, serialization, etc.
"""

import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ed25519
from cryptography.hazmat.backends import default_backend


def serialize_ssh_public_key(public_key_pem: str) -> str:
    """
    Convert a PEM-encoded public key to OpenSSH format.

    Args:
        public_key_pem (str): The PEM-encoded public key.

    Returns:
        str: The public key in OpenSSH format.

    Raises:
        ValueError: If the key type is unsupported.
    """
    public_key = serialization.load_pem_public_key(
        public_key_pem.encode(),
        backend=default_backend()
    )

    if isinstance(public_key, rsa.RSAPublicKey):
        return public_key.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH
        ).decode("utf-8")
    elif isinstance(public_key, ed25519.Ed25519PublicKey):
        return public_key.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH
        ).decode("utf-8")
    else:
        raise ValueError("Unsupported public key type for OpenSSH serialization.")


def handle_rsa_keys(role_keys: dict, ssh_dir: Path) -> None:
    """
    Handle RSA private/public key creation and saving.
    
    Args:
        role_keys (dict): Dictionary containing key data for the role.
        ssh_dir (Path): Directory in which to place the keys.
    """
    if "rsa_private_key" not in role_keys or "rsa_public_key" not in role_keys:
        return  # no RSA keys to handle

    rsa_private_key_path = ssh_dir / "id_rsa"
    rsa_public_key_path = ssh_dir / "id_rsa.pub"

    # Standardize RSA private key format
    private_key = serialization.load_pem_private_key(
        role_keys["rsa_private_key"].encode(),
        password=None,
        backend=default_backend()
    )
    standardized_private_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Write RSA private key
    with open(rsa_private_key_path, "w", encoding="utf-8") as f:
        f.write(standardized_private_key.decode("utf-8"))
    os.chmod(rsa_private_key_path, 0o600)  # restrict permissions

    # Serialize RSA public key to OpenSSH format
    rsa_ssh_public_key = serialize_ssh_public_key(role_keys["rsa_public_key"])
    with open(rsa_public_key_path, "w", encoding="utf-8") as f:
        f.write(rsa_ssh_public_key)


def handle_ed25519_keys(role_keys: dict, ssh_dir: Path) -> None:
    """
    Handle Ed25519 private/public key creation and saving.
    
    Args:
        role_keys (dict): Dictionary containing key data for the role.
        ssh_dir (Path): Directory in which to place the keys.
    """
    if "ed25519_private_key" not in role_keys or "ed25519_public_key" not in role_keys:
        return  # no Ed25519 keys to handle

    ed25519_private_key_path = ssh_dir / "id_ed25519"
    ed25519_public_key_path = ssh_dir / "id_ed25519.pub"

    # Standardize Ed25519 private key format
    private_key = serialization.load_pem_private_key(
        role_keys["ed25519_private_key"].encode(),
        password=None,
        backend=default_backend()
    )
    standardized_private_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Write Ed25519 private key
    with open(ed25519_private_key_path, "w", encoding="utf-8") as f:
        f.write(standardized_private_key.decode("utf-8"))
    os.chmod(ed25519_private_key_path, 0o600)  # restrict permissions

    # Serialize Ed25519 public key to OpenSSH format
    ed25519_ssh_public_key = serialize_ssh_public_key(role_keys["ed25519_public_key"])
    with open(ed25519_public_key_path, "w", encoding="utf-8") as f:
        f.write(ed25519_ssh_public_key)
