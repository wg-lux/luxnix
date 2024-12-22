"""
Command-line script to initialize or update user keys via KeyFileManager.
"""

import os
from datetime import datetime

# Adjust the relative import as needed based on your project structure.
# For example, if KeyFileManager is at managers/key_file_manager.py:
from lx_admin.managers.key_file_manager import KeyFileManager, generate_key_pair




def process_users(input_yaml_path: str, output_yaml_path: str) -> None:
    """
    Loads users from `input_yaml_path`, initializes or updates keys for each role,
    and then saves the result to `output_yaml_path`.

    This demonstrates how to programmatically use KeyFileManager to populate keys.
    """
    # Initialize the KeyFileManager
    manager = KeyFileManager(input_yaml_path)
    users_data = manager.get_users_data()

    current_time = datetime.now().isoformat()

    for user in users_data:
        user_name = user["name"]
        # For each role@host in the user's roles
        for role_host in user["roles"]:
            # If the user doesn't yet have keys for that role, create them:
            if role_host not in user["keys"]:
                # Generate RSA
                rsa_priv, rsa_pub = generate_key_pair("rsa")
                manager.add_user_key(user_name, role_host, "rsa", rsa_priv, rsa_pub)

                # Generate Ed25519
                ecd_priv, ecd_pub = generate_key_pair("ed25519")
                manager.add_user_key(user_name, role_host, "ed25519", ecd_priv, ecd_pub)

                # Generate SOPS AGE
                sops_priv, sops_pub = generate_key_pair("sops_age")
                manager.add_user_key(user_name, role_host, "sops_age", sops_priv, sops_pub)

            else:
                # Optionally auto-update or skip if keys exist
                # This code is just an example to demonstrate how you might do it
                pass

    # Force save to the new output path
    # The KeyFileManager saves to self.file_path by default,
    # so you can replace the path before saving if needed:
    manager.file_path = output_yaml_path
    manager._save_file()

    print(f"Processed users saved to: {output_yaml_path}")


if __name__ == "__main__":
    # Adjust these paths to your needs
    input_file = "lx-base-identities.yaml"
    output_file = "data/user-keygen/identities.yaml"

    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    process_users(input_file, output_file)
