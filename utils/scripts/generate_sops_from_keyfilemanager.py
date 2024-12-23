"""
generate_sops_from_keyfilemanager.py

A small script that:
  1) Iterates over all users & roles in KeyFileManager
  2) Creates default home/system rules for each role
  3) Saves a fresh .sops.yaml with updated patterns
"""

import os
from lx_admin.managers.key_file_manager import KeyFileManager
from lx_admin.managers.sops_secret_manager import SopsSecretManager

def generate_sops_from_keyfile(key_file_path, sops_file_path, lx_dir=".."):
    # Step 1: Initialize KeyFileManager and SopsSecretManager
    kfm = KeyFileManager(key_file_path)
    sops_mgr = SopsSecretManager(
        lx_dir=lx_dir,
        sops_file_path=sops_file_path,
        key_file_path=key_file_path
    )

    # Step 2: Iterate over every user + role in KeyFileManager
    users_data = kfm.get_users_data()
    for user_info in users_data:
        user_name = user_info["name"]
        for role_host in user_info["roles"]:
            # Force creation of default rules for each user@host
            # This also ensures the sops_age key is generated if missing
            sops_mgr.add_or_update_user_identity(
                user_name=user_name,
                role_host=role_host,
                force_new_key=False  # or True if you want fresh keys
            )

    print("[INFO] Done regenerating default rules for all user@roles in KeyFileManager.")
    print(f"[INFO] The newly created .sops.yaml is at: {sops_file_path}")

if __name__ == "__main__":
    # Example usage:
    key_file = "data/luxnix-identities.yaml"
    sops_file = "../.sops.yaml"

    # If you had an old .sops.yaml, you might want to move or remove it first
    if os.path.exists(sops_file):
        os.rename(sops_file, sops_file + ".old")

    generate_sops_from_keyfile(key_file, sops_file)
