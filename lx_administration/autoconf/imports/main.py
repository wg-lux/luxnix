from pathlib import Path
from . import (
    load_all_host_facts,
    load_inventory_hostfile,
)
import warnings
from lx_administration.autoconf.imports.utils import is_home_only_host, load_home_host_vars

from lx_administration.logging import log_heading, get_logger
from lx_administration.models import MergedHostVars
from lx_administration.yaml.dump import dump_yaml, format_yaml


def home_etl(ansible_root: Path, autoconf_out: Path, logger=None):
    if not logger:
        logger = get_logger("home_etl", reset=True)

    logger.info("Running home_etl...")

    home_merged_vars_out = autoconf_out / "home_merged_vars"
    home_merged_vars_out.mkdir(parents=True, exist_ok=True)

    # Load the fully merged vars per host
    ansible_inventory_dir = ansible_root / "inventory"
    home_host_vars = load_home_host_vars(ansible_inventory_dir)

    for hostname, merged_dict in home_host_vars.items():
        try:
            MergedHostVars(**merged_dict)
        except Exception as e:
            logger.warning(f"Invalid home vars for {hostname}: {e}")
            continue

        dump_yaml(merged_dict, home_merged_vars_out / f"{hostname}.yml", format_yaml)

    logger.info("Finished home_etl.")


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
        logger.error(f"Host facts directory not found: {host_facts_dir}")
        return None, set()

    if not ansible_inventory_dir.exists():
        logger.error(f"Ansible inventory directory not found: {ansible_inventory_dir}")
        return None, set()

    if not inventory_file.exists():
        logger.error(f"Inventory file not found: {inventory_file}")
        return None, set()

    inventory = load_inventory_hostfile(inventory_file)

    host_facts = load_all_host_facts(host_facts_dir)

    for host, facts in host_facts.items():
        inventory.hostname_update_ansible_facts(host, facts)

    for host in inventory.all:
        host.init_ansible_role_names()

    inventory.save_to_file(autoconf_out / "inventory.yml")

    merged_vars_out = autoconf_out / "merged_vars"
    merged_vars_out.mkdir(exist_ok=True)
    inventory.validate_inventory()

    home_only_hosts = set()
    for host in inventory.all:
        if is_home_only_host(host):
            logger.info(f"Skipping system config for home-only host: {host.hostname}")
            if host.hostname:
                home_only_hosts.add(host.hostname)
            continue
        if not host.hostname:
            logger.warning("Host without hostname found; skipping")
            continue
        merged_vars = inventory.export_merged_host_vars(host.hostname)

        try:
            MergedHostVars(**merged_vars)
        except Exception as e:
            warnings.warn(f"Invalid merged_vars for {host.hostname}: {e}")

        dump_yaml(
            merged_vars,
            merged_vars_out / f"{host.hostname}.yml",
            format_yaml,
        )

    inventory.save_to_file(autoconf_out / "inventory.yml")
    return inventory, home_only_hosts


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

    inventory, home_only_hosts = ansible_etl(
        ansible_root, autoconf_out, subnet, logger=logger
    )
    return inventory, home_only_hosts
