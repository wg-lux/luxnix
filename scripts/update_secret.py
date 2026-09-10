import argparse
import getpass
import sys
import warnings
from lx_administration.models.vault import Vault
from lx_administration.password import PasswordGenerator

# example usage:
# Lets say you named postgres_host_main_password
# change export SECRET_NAME=postgres_host_main_password as required


def parse_bool(value):
    return str(value).lower() in ("true", "1", "yes")


def parse_args(argv=None):
    """Parse and return command line arguments for secret management.

    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description="Update a secret in the vault.", allow_abbrev=False
    )
    arguments = sys.argv[1:] if argv is None else argv
    if any(
        arg == "--custom-value" or arg.startswith("--custom-value=")
        for arg in arguments
    ):
        parser.error(
            "--custom-value is unsafe and no longer accepted; use --prompt-value"
        )
    parser.add_argument(
        "--vault-dir", default="~/.lxv/", help="Path to vault directory"
    )
    parser.add_argument(
        "--vault-key", default="~/.lxv.key", help="Path to vault key file"
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
        default=True,
        help="Require uppercase characters",
    )
    parser.add_argument(
        "--require-lower",
        type=parse_bool,
        default=True,
        help="Require lowercase characters",
    )
    parser.add_argument(
        "--require-digits",
        type=parse_bool,
        default=True,
        help="Require digits",
    )
    parser.add_argument(
        "--require-special",
        type=parse_bool,
        default=False,
        help="Require special characters",
    )
    parser.add_argument(
        "--prompt-value",
        action="store_true",
        help="Read a replacement value at a hidden terminal prompt",
    )
    return parser.parse_args(arguments)


def main():
    args = parse_args()
    vault = Vault.load_dir(args.vault_dir, args.vault_key)

    if args.prompt_value:
        # Never fall back to an echoed prompt when no terminal is available.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            new_value = getpass.getpass("Replacement secret: ")
        if not new_value:
            raise ValueError("Replacement secret must not be empty")
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
    generated_kind = "password" if args.mode == "password" else "passphrase"
    print(f"Updated secret '{args.secret_name}' with new {generated_kind}.")


if __name__ == "__main__":
    main()
