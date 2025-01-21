from pathlib import Path
import yaml
from . import (
    load_all_host_facts,
    load_inventory_hostfile,
)
import warnings

from lx_administration.logging import log_heading, get_logger
from lx_administration.models import MergedHostVars
from lx_administration.yaml.dump import dump_yaml, ansible_lint, format_yaml


def ansible_etl(ansible_root: Path, autoconf_out: Path, subnet: str, logger=None):
    if not logger:
        logger = get_logger("ansible_etl", reset=True)

    log_heading(logger, "------------ansible_etl------------")

    ansible_inventory_dir = ansible_root / "inventory"
    inventory_file = ansible_inventory_dir / "hosts.ini"
    host_facts_dir = ansible_root / "cmdb"
    log_dir = autoconf_out / "logs"
    log_dir.mkdir(exist_ok=True)

    if not host_facts_dir.exists():
        # raise exception
        logger.error(f"Host facts directory not found: {host_facts_dir}")
        return

    if not ansible_inventory_dir.exists():
        # raise exception
        logger.error(f"Ansible inventory directory not found: {ansible_inventory_dir}")
        return

    if not inventory_file.exists():
        # raise exception
        logger.error(f"Inventory file not found: {inventory_file}")
        return

    # Load inventory
    inventory = load_inventory_hostfile(inventory_file)

    host_facts = load_all_host_facts(host_facts_dir)

    for host, facts in host_facts.items():
        inventory.hostname_update_ansible_facts(host, facts)

    inventory.save_to_file(autoconf_out / "inventory.yml")

    merged_vars_out = autoconf_out / "merged_vars"
    merged_vars_out.mkdir(exist_ok=True)

    for host in inventory.all:
        merged_vars = inventory.export_merged_host_vars(host.hostname)

        # validate merged_vars
        try:
            MergedHostVars(**merged_vars)
        except Exception as e:
            warnings.warn(f"Invalid merged_vars for {host.hostname}: {e}")

        dump_yaml(
            merged_vars,
            merged_vars_out / f"{host.hostname}.yml",
            format_yaml,
            # ansible_lint,
        )

    #     host_configs[host] = merged_config
    inventory.save_to_file(autoconf_out / "inventory.yml")
    return inventory


def pipe(
    ansible_root: Path, autoconf_out: Path, subnet: str = "172.16.255.0", logger=None
):
    if not logger:
        logger = get_logger("autoconf_imports_main_pipe", reset=True)

    log_heading(logger, "------------autoconf/imports/main:pipe------------")
    logger.info(f"ansible_root: {ansible_root}")
    logger.info(f"autoconf_out: {autoconf_out}")
    logger.info(f"subnet: {subnet}\n\n\n")
    if not autoconf_out.exists():
        autoconf_out.mkdir(exist_ok=True)

    inventory = ansible_etl(ansible_root, autoconf_out, subnet, logger=logger)
    return inventory
