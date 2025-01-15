import os
import subprocess
from typing import Any


def create_openssh_keys(
    output_dir, key_name="id_rsa", passphrase=None, key_type="rsa"
) -> dict[str, Any]:
    """
    Create OpenSSH key pair.

    Args:
        output_dir (str): Directory where the keys will be saved.
        key_name (str): Base name for the keys. Defaults to 'id_rsa'.
        passphrase (str): Optional passphrase for the private key. Defaults to None.
        key_type (str): Type of the key to generate ('rsa' or 'ed25519').
        Defaults to 'rsa'.

    Returns:
        dict: Paths to the generated private and public keys.
    """
    # Validate inputs
    if not key_name or not key_name.strip():
        raise ValueError("Key name must not be empty or whitespace.")
    if key_type not in ["rsa", "ed25519"]:
        raise ValueError("Key type must be 'rsa' or 'ed25519'.")

    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Define paths for private and public keys
    private_key_path = os.path.join(output_dir, key_name)
    public_key_path = f"{private_key_path}.pub"

    # Prepare ssh-keygen command
    cmd = [
        "ssh-keygen",
        "-t",
        key_type,
        "-f",
        private_key_path,
        "-N",
        passphrase or "",  # Empty passphrase if None
        "-q",  # Quiet mode
    ]

    # Add bit size for RSA keys
    if key_type == "rsa":
        cmd.extend(["-b", "4096"])

    # Run the ssh-keygen command
    subprocess.run(cmd, check=True)

    return {"private_key": private_key_path, "public_key": public_key_path}
