#!/usr/bin/env python3

from lx_administration.models import Vault


def main():
    vault = Vault()  # ...you may specify custom paths or arguments if needed...
    vault.load_or_create()


if __name__ == "__main__":
    main()
