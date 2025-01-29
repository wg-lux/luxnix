#!/usr/bin/env python3

from lx_administration.models import Vault, Secret
from lx_administration.logging import get_logger
from lx_administration.yaml import dump_yaml, format_yaml

import os
import shutil
from pathlib import Path

from typing import List


BASE_LOGGER = get_logger("lxv-postgres-secrets", reset=True)


def main(logger=None):
    if not logger:
        logger = BASE_LOGGER

    dirpath = Path("~/.lxv").expanduser()
    keypath = Path("~/.lsv.key").expanduser()

    vault = Vault(
        dir=dirpath.resolve().as_posix(),
        key=keypath.resolve().as_posix(),
        ansible_cfg="./conf/ansible.cfg",
        key_owner_types=["local", "roles", "services", "luxnix", "clients"],
        default_system_users=["admin"],
        subnet="172.16.255.",
    )  # ...you may specify custom paths or arguments if needed...

    logger.info("Loading or creating vault...")
    vault = vault.load_or_create()
    logger.info("Vault loaded or created successfully!")

    logger.info("Syncing inventory...")
    vault.sync_inventory("./autoconf/inventory.yml", logger=logger)
