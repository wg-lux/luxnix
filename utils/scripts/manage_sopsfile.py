"""
manage_sopsfile.py

Script to create or modify a .sops.yaml file using SopsSecretManager.
By default, each save will create a new versioned file (e.g. 0002.sops.yaml).
You can pass --no-new-version if you want to overwrite in place.

python scripts/manage_sopsfile.py --file data/sopsfiles/0001.sops.yaml \
    --add-rule "./homes/x86_64-linux/admin@hostname/secrets/*" \
    "admin@hostname"

python scripts/manage_sopsfile.py --file data/sopsfiles/0002.sops.yaml --update-rule 0 "admin@host1,dev@host2"

"""

import argparse
import os
from lx_admin.managers.sops_secret_manager import SopsSecretManager


def main():
    parser = argparse.ArgumentParser(
        description="Create or modify a .sops.yaml file."
    )
    parser.add_argument("--file", default="sopsfiles/0001.sops.yaml",
                        help="Path to the .sops.yaml file. Defaults to sopsfiles/0001.sops.yaml.")
    parser.add_argument("--add-rule", nargs=2, metavar=("GLOB", "IDENTITIES"),
                        help="Add a new creation rule. Usage: --add-rule ./secrets/* 'admin@host1,dev@host2'")
    parser.add_argument("--update-rule", nargs=2, metavar=("INDEX", "IDENTITIES"),
                        help="Update the rule at INDEX with a new list of identities. Usage: --update-rule 0 'admin@host1'")
    args = parser.parse_args()

    manager = SopsSecretManager(args.file)

    # If the user wants to add a rule
    if args.add_rule:
        filepath_glob, identities_str = args.add_rule
        identities_list = [x.strip() for x in identities_str.split(",")]
        manager.add_or_update_rule(filepath_glob, identities_list)
        print(f"Added/updated rule for glob='{filepath_glob}', identities={identities_list}")

    # If the user wants to update an existing rule by index
    if args.update_rule:
        index_str, identities_str = args.update_rule
        index = int(index_str)
        identities_list = [x.strip() for x in identities_str.split(",")]
        manager.update_rule_keys(index, identities_list)
        print(f"Updated rule index={index} with identities={identities_list}")

    manager.save_sops_file()


if __name__ == "__main__":
    main()
