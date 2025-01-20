from pathlib import Path
from lx_administration.logging import get_logger
import pprint
import logging

from lx_administration.models.ansible import AnsibleInventory


def load_inventory_hostfile(
    file: Path, logger=None, subnet: str = "172.16.255."
) -> AnsibleInventory:
    """Load ansiblie hosts.ini file"""
    if not logger:
        logger = get_logger(
            "load_inventory_hostfile", reset=True, log_level=logging.DEBUG
        )

    inventory = AnsibleInventory.load_from_file(file, subnet=subnet)

    return inventory
