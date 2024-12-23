#!/usr/bin/env python3
"""
create_secret_demo.py

A demonstration script for creating an encrypted secret file
targeted at either a system or a home environment. By default:

1. We automatically ensure the user identity is present in KeyFileManager,
   generating default sops rules for {lxDir}/homes/... and {lxDir}/systems/...
2. We use create_secret(...) to place and encrypt the source file in 
   the correct 'secrets/{general|hidden}' folder.
3. The file is encrypted with sops, which respects the default rules 
   plus the backup key.

Usage example:
--------------
python scripts/create_secret_demo.py \
    --lx-dir .. \
    --sops-file ../.sops.yaml \
    --key-file data/luxnix-identities.yaml \
    --system-or-home home \
    --user-or-host "admin@gc-06" \
    --hidden false \
    --source-file "/home/admin/luxnix/utils/data/secrets/postgres-main/host.yaml"
"""

import argparse
import os
from lx_admin.managers.sops_secret_manager import SopsSecretManager


def main():
    parser = argparse.ArgumentParser(
        description="Demo script for creating an encrypted secret file using SopsSecretManager."
    )

    parser.add_argument("--lx-dir", default="..",
                        help="Path to the top-level Nix directory (default: '..').")
    parser.add_argument("--sops-file", default="../.sops.yaml",
                        help="Path to the main .sops.yaml file (default: '../.sops.yaml').")
    parser.add_argument("--key-file", default="data/luxnix-identities.yaml",
                        help="Path to the user identity YAML (default: 'data/luxnix-identities.yaml').")

    parser.add_argument("--system-or-home", choices=["system", "home"], required=True,
                        help="Set to 'system' or 'home'. Affects how the secret path is built.")
    parser.add_argument("--user-or-host", required=True,
                        help="If system, pass the host (e.g. 'myhost'); if home, pass 'alice@myhost'.")
    parser.add_argument("--hidden", default="false",
                        help="If 'true', the secret goes into secrets/hidden; otherwise secrets/general.")
    parser.add_argument("--source-file", required=True,
                        help="Path to the plaintext file we want to encrypt.")
    args = parser.parse_args()

    # Convert 'true'/'false' to bool
    hidden_bool = (args.hidden.lower() == "true")

    # 1. Initialize the manager
    sops_mgr = SopsSecretManager(
        lx_dir=args.lx_dir,
        sops_file_path=args.sops_file,
        key_file_path=args.key_file
    )

    # 2. If we are in "home" mode, we expect user@host. If "system", we just have a hostname.
    #    We'll automatically update that user identity in KeyFileManager 
    #    so sops rules are set for {lxDir}/homes/... or {lxDir}/systems/...
    #    (We pass the same strings for user_name and role_host if we don't need distinct userName.)
    if args.system_or_home == "home":
        if "@" not in args.user_or_host:
            raise ValueError("For 'home', you must provide user@host (e.g., 'alice@myhost').")
        # We'll parse out the user portion if desired, or re-use the entire string as both
        full_role_host = args.user_or_host
        user_name = args.user_or_host.split("@")[0]  # e.g. "alice"
    else:
        # system => user-or-host is just the host
        full_role_host = args.user_or_host
        user_name = full_role_host  # In some setups, you might prefer "system" or something else

    # Add or update the identity => automatically sets up default home/system rules
    sops_mgr.add_or_update_user_identity(
        user_name=user_name,
        role_host=full_role_host
    )
    print(f"[INFO] Identity {user_name}/{full_role_host} updated with default sops rules.")

    # 3. Now create the secret using the manager's create_secret function
    #    This will encrypt the file into either secrets/general or secrets/hidden 
    #    under {lxDir}/homes... or {lxDir}/systems..., accordingly.
    encrypted_path = sops_mgr.create_secret(
        system_or_home=args.system_or_home,
        user_or_host=args.user_or_host,
        hidden=hidden_bool,
        source_file=args.source_file
    )

    print(f"Secret created and encrypted at: {encrypted_path}")


if __name__ == "__main__":
    main()
