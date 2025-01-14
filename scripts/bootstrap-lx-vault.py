#!/usr/bin/env python3
import sys
from pathlib import Path

from lx_administration.vault import Vault


def main():
    vault = Vault()  # ...you may specify custom paths or arguments if needed...
    hosts = vault.bootstrap_hosts()

    vault.sync()


if __name__ == "__main__":
    main()
