"""
init_identity.py

Script to generate a new identity file if needed, explore its contents (e.g., list users and roles),
and display basic information about identities.

Usage:
# 1) Create or verify an identity file exists, do not show anything:
python scripts/init_identity.py

# 2) Show the details (users, roles, partial keys):
python scripts/init_identity.py --show
"""

import argparse
import os
from lx_admin.managers import KeyFileManager

def main():
    parser = argparse.ArgumentParser(
        description="Generate or explore an identity file (YAML) using KeyFileManager."
    )
    parser.add_argument("--file", default="data/luxnix-identities.yaml",
                        help="Path to the identity YAML file.")
    parser.add_argument("--show", action="store_true",
                        help="If set, displays the list of users/roles/keys.")
    args = parser.parse_args()

    # If the file doesn't exist, create a minimal structure
    if not os.path.exists(args.file):
        # Create a minimal YAML structure: {"users": []}
        with open(args.file, "w", encoding="utf-8") as f:
            f.write("users: []\n")
        print(f"Created new identity file at '{args.file}'.")

    manager = KeyFileManager(args.file)

    if args.show:
        users_data = manager.get_users_data()
        print(f"Identity file: {args.file}")
        for user in users_data:
            print(f" - User: {user['name']}")
            print(f"     Roles: {user['roles']}")
            print(f"     Keys: ")
            for role, keys_dict in user['keys'].items():
                print(f"       Role: {role}")
                for k, v in keys_dict.items():
                    if "key" in k:
                        # Avoid printing entire private key
                        short_val = v[:40].replace("\n", " ") + "..."
                        print(f"         {k}: {short_val}")
                    else:
                        print(f"         {k}: {v}")

if __name__ == "__main__":
    main()
