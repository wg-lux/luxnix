import logging
from pathlib import Path

from lx_administration.logging import get_logger
from lx_administration.models.ansible import AnsibleInventory


def load_inventory_hostfile(
    file: Path,
    subnet: str,
    logger: logging.Logger | None = None,
) -> AnsibleInventory:
    """Load an Ansible hosts.ini file using the configured managed subnet."""
    if logger is None:
        logger = get_logger(
            "load_inventory_hostfile", reset=True, log_level=logging.DEBUG
        )

    inventory = AnsibleInventory.load_from_hosts_ini(
        file,
        subnet=subnet,
        logger=logger,
    )

    return inventory
