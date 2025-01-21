#!/usr/bin/env python3

from lx_administration.models import Vault
from lx_administration.logging import get_logger

BASE_LOGGER = get_logger("bootstrap-lx-vault", reset=True)


def main(logger=None):
    if not logger:
        logger = BASE_LOGGER

    vault = Vault(
        dir="~/.lxv",
        key="~/.lsv.key",
        key_owner_types=["local", "roles", "services", "luxnix", "clients"],
        default_system_users=["admin"],
        subnet="172.16.255.",
    )  # ...you may specify custom paths or arguments if needed...

    logger.info("Loading or creating vault...")
    vault.load_or_create()
    logger.info("Vault loaded or created successfully!")

    logger.info("Syncing inventory...")
    vault.sync_inventory("./autoconf/inventory.yml")


if __name__ == "__main__":
    main()
