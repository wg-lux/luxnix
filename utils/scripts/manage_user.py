"""
manage_user.py

Script to add or remove users from the identity file.

Example:
# Add a user "alice" to the identity file:
python scripts/manage_user.py --add-user alice

# Add "admin@host1" role to user "alice" immediately upon creation
python scripts/manage_user.py --add-user alice --add-role admin@host1

# Remove user "bob" entirely:
python scripts/manage_user.py --remove-user bob

# In real usage, you might separate these options (or unify them in a single script).

"""

import argparse
from lx_admin.managers.key_file_manager import KeyFileManager

def main():
    parser = argparse.ArgumentParser(
        description="Add or remove users in the identity YAML file."
    )
    parser.add_argument("--file", default="data/luxnix-identities.yaml",
                        help="Path to the identity YAML file.")
    parser.add_argument("--add-user", type=str,
                        help="Name of the user to add.")
    parser.add_argument("--remove-user", type=str,
                        help="Name of the user to remove.")
    parser.add_argument("--add-role", type=str,
                        help="Add a role (e.g. admin@hostname) to the last specified user.")
    parser.add_argument("--remove-role", type=str,
                        help="Remove a role from the last specified user.")
    args = parser.parse_args()

    manager = KeyFileManager(args.file)

    # If user specified add-user
    if args.add_user:
        manager.add_user(args.add_user)
        print(f"User '{args.add_user}' added.")

        # If also specified add-role
        if args.add_role:
            manager.add_user_role(args.add_user, args.add_role)
            print(f"Role '{args.add_role}' added to user '{args.add_user}'.")

    # If user specified remove-user
    if args.remove_user:
        manager.remove_user(args.remove_user)
        print(f"User '{args.remove_user}' removed.")

    # If user only wants to add or remove a role for an existing user
    # we can do that, but we need to know which user to do it for
    if args.add_role and not args.add_user:
        # For demonstration, let's assume the user we want to add a role to
        # is the --add-user or --remove-user. If not, we might prompt or fail
        print("Error: --add-role was used but no user was specified. Provide --add-user or expand script logic.")
    
    if args.remove_role and not args.remove_user:
        # Similarly
        print("Error: --remove-role was used but no user was specified. Provide --remove-user or expand script logic.")

if __name__ == "__main__":
    main()
