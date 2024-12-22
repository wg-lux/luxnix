"""
Utilities for handling SOPS Age key deployment.
"""

import os
from pathlib import Path


def deploy_sops_age_keys(role_keys: dict, role_host: str, base_dir: str) -> None:
    """
    Deploy SOPS age keys to .config/sops/age/{role_host}.

    Args:
        role_keys (dict): Dictionary containing key data for the role.
        role_host (str): The role@host combination.
        base_dir (str): Base directory where .config/sops/age/ is located.
    """
    # Check if we have SOPS Age keys
    if "sops_age_public_key" not in role_keys or "sops_age_private_key" not in role_keys:
        return  # no SOPS Age keys to deploy

    age_config_dir = Path(base_dir) / ".config" / "sops" / "age" / role_host
    age_config_dir.mkdir(parents=True, exist_ok=True)

    # Deploy public key
    age_public_key_path = age_config_dir / "keys.pub"
    with open(age_public_key_path, "w", encoding="utf-8") as f:
        f.write(role_keys["sops_age_public_key"].strip() + "\n")

    # Deploy private key
    age_private_key_path = age_config_dir / "keys.txt"
    with open(age_private_key_path, "w", encoding="utf-8") as f:
        f.write(role_keys["sops_age_private_key"].strip() + "\n")
