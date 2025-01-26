#!/usr/bin/env python3

from lx_administration.models import Vault
from lx_administration.logging import get_logger

import os
import shutil
from pathlib import Path

BASE_LOGGER = get_logger("bootstrap-lx-vault", reset=True)


def main(logger=None):
    if not logger:
        logger = BASE_LOGGER

    ##### PROTOTYPING #####
    # remove directory and key if they exist
    dirpath = Path("~/.lxv").expanduser()
    keypath = Path("~/.lsv.key").expanduser()

    # if dirpath.exists():
    #     shutil.rmtree(dirpath, ignore_errors=True)
    # if keypath.exists():
    #     os.remove(keypath)
    #######################

    vault = Vault(
        dir=dirpath.resolve().as_posix(),
        key=keypath.resolve().as_posix(),
        key_owner_types=["local", "roles", "services", "luxnix", "clients"],
        default_system_users=["admin"],
        subnet="172.16.255.",
    )  # ...you may specify custom paths or arguments if needed...

    logger.info("Loading or creating vault...")
    vault = vault.load_or_create()
    logger.info("Vault loaded or created successfully!")

    logger.info("Syncing inventory...")
    vault.sync_inventory("./autoconf/inventory.yml", logger=logger)

    logger.info(vault.summary())


if __name__ == "__main__":
    main()
