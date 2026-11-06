"""Retired central identity-salt launcher: fail before credentials or network access."""


def main() -> None:
    raise SystemExit(
        "Central identity salt provisioning is disabled; "
        "preserve the established local keyring"
    )


if __name__ == "__main__":
    main()
