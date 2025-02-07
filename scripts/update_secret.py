import argparse
from lx_administration.models.vault.manager import Vault
from lx_administration.password.generator import PasswordGenerator

# example usage:
# Lets say you named postgres_host_main_password
# TODO @hamzahsn: Add the following to the docs

# change export SECRET_NAME=postgres_host_main_password as required

_bash = """
## CHANGE THIS AS REQUIRED
export SECRET_TEMPLATE_NAME=keycloak_host
export SECRET_NAME=keycloak_host_password


export VAULT_DIR=~/.lxv
export VAULT_KEY=~/.lsv.key
export MODE=password
export KEY_LENGTH=20
export MIN_LENGTH=12
export NUM_WORDS=5
export REQUIRE_UPPER=true
export REQUIRE_LOWER=true
export REQUIRE_DIGITS=true
export REQUIRE_SPECIAL=false

# Look up the secret in VAULT_DIR/vault.yml 
# (Secret with this name must exist)
# (Secret with this name has a path and an existing encrypted file)
export SECRET_PATH=~/.lxv/secrets/system_password/roles/$SECRET_TEMPLATE_NAME/$SECRET_NAME
ansible-vault view $SECRET_PATH

# run script
python scripts/update_secret.py --secret-name $SECRET_NAME --mode $MODE --key-length $KEY_LENGTH --min-length $MIN_LENGTH --num-words $NUM_WORDS --require-upper $REQUIRE_UPPER --require-lower $REQUIRE_LOWER --require-digits $REQUIRE_DIGITS --require-special $REQUIRE_SPECIAL

# verify the secret has been updated
ansible-vault view $SECRET_PATH
"""

# python update_secret.py --secret-name myapp_password --mode password --key-length 20
# python update_secret.py --secret-name myapp_passphrase --mode passphrase --num-words 5
# python update_secret.py --secret-name custom_secret --custom-value "my-custom-value"


def parse_bool(value):
    return str(value).lower() in ("true", "1", "yes")


def parse_args():
    """Parse and return command line arguments for secret management.

    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(description="Update a secret in the vault.")
    parser.add_argument(
        "--vault-dir", default="~/.lxv/", help="Path to vault directory"
    )
    parser.add_argument(
        "--vault-key", default="~/.lsv.key", help="Path to vault key file"
    )
    parser.add_argument(
        "--secret-name", required=True, help="Name of the secret to update"
    )
    parser.add_argument(
        "--mode",
        choices=["password", "passphrase"],
        default="password",
        help="Generation mode",
    )
    parser.add_argument(
        "--key-length", type=int, default=16, help="Length for generated password"
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=12,
        help="Minimum length for generated password",
    )
    parser.add_argument(
        "--num-words", type=int, default=4, help="Number of words for passphrase"
    )
    parser.add_argument(
        "--require-upper",
        type=parse_bool,
        default=False,
        help="Require uppercase characters",
    )
    parser.add_argument(
        "--require-lower",
        type=parse_bool,
        default=False,
        help="Require lowercase characters",
    )
    parser.add_argument(
        "--require-digits",
        type=parse_bool,
        default=False,
        help="Require digits",
    )
    parser.add_argument(
        "--require-special",
        type=parse_bool,
        default=False,
        help="Require special characters",
    )
    parser.add_argument(
        "--custom-value", help="Use this value instead of generating one"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    vault = Vault.load_dir(args.vault_dir, args.vault_key)

    if args.custom_value:
        new_value = args.custom_value
    else:
        pg = PasswordGenerator(
            mode=args.mode,
            key_length=args.key_length,
            num_words=args.num_words,
            min_length=args.min_length,
            require_upper=args.require_upper,
            require_lower=args.require_lower,
            require_digits=args.require_digits,
            require_special=args.require_special,
        )
        new_value = (
            pg.generate_random_password()
            if args.mode == "password"
            else pg.generate_random_passphrase()
        )

    vault.update_secret_value(args.secret_name, new_value)
    print(
        f"Updated secret '{args.secret_name}' with new {'password' if args.mode=='password' else 'passphrase'}."
    )


if __name__ == "__main__":
    main()
