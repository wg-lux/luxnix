from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from lx_administration.logging import get_logger, log_heading
from lx_administration.models import MergedHostVars
from lx_administration.models.ansible import AnsibleInventory

from ..errors import AutoconfPipelineError, AutoconfSourceNotFoundError
from ..layout import AutoconfOutputLayout, AutoconfSourceLayout
from .ansible_facts import load_all_host_facts
from .ansible_inventory import load_inventory_hostfile
from .artifacts import (
    HostVariables,
    ValidatedHosts,
    write_merged_host_variables,
    write_system_intermediates,
)
from .sources import load_home_host_vars


def _require_directory(path: Path, label: str) -> None:
    if not path.is_dir():
        raise AutoconfSourceNotFoundError(f"{label} not found: {path}")


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise AutoconfSourceNotFoundError(f"{label} not found: {path}")


def build_home_merged_variables(
    ansible_root: Path,
    autoconf_out: Path,
    logger: logging.Logger | None = None,
) -> None:
    """Validate and write merged Home Manager variables."""
    layout = AutoconfOutputLayout(autoconf_out)
    source = AutoconfSourceLayout(ansible_root)
    if logger is None:
        logger = get_logger(
            "autoconf_home_import",
            log_dir=layout.log_dir,
            reset=True,
        )

    logger.info("Loading Home Manager inventory variables")

    home_host_vars = load_home_host_vars(source.inventory.root)

    validated_hosts: ValidatedHosts = []
    for hostname in sorted(home_host_vars):
        merged_dict: HostVariables = home_host_vars[hostname]
        try:
            MergedHostVars.model_validate(merged_dict)
        except ValidationError as exc:
            raise AutoconfPipelineError(
                f"Invalid Home Manager variables for {hostname} ({type(exc).__name__})"
            ) from exc
        validated_hosts.append((hostname, merged_dict))

    write_merged_host_variables(
        layout.home_vars_dir,
        validated_hosts,
    )

    logger.info("Finished loading Home Manager inventory variables")


def build_system_merged_variables(
    ansible_root: Path,
    autoconf_out: Path,
    subnet: str,
    system_group: str,
    logger: logging.Logger | None = None,
) -> AnsibleInventory:
    """Validate inventory data and write merged NixOS system variables."""
    layout = AutoconfOutputLayout(autoconf_out)
    source = AutoconfSourceLayout(ansible_root)
    if logger is None:
        logger = get_logger(
            "autoconf_system_import",
            log_dir=layout.log_dir,
            reset=True,
        )

    log_heading(logger, "Load Ansible inventory")

    _require_directory(source.inventory.root, "Ansible inventory directory")
    _require_file(source.inventory.hosts_file, "Ansible inventory")

    inventory = load_inventory_hostfile(source.inventory.hosts_file, subnet=subnet)

    host_facts = load_all_host_facts(source.facts_dir)

    for hostname in sorted(host_facts):
        inventory.hostname_update_ansible_facts(hostname, host_facts[hostname])

    for host in inventory.all:
        host.init_ansible_role_names()

    if system_group not in inventory.get_group_names():
        raise AutoconfPipelineError(f"System inventory group not found: {system_group}")
    system_hosts = [
        host for host in inventory.all if system_group in host.ansible_group_names
    ]
    if not system_hosts:
        raise AutoconfPipelineError(
            f"System inventory group has no hosts: {system_group}"
        )

    validated_hosts: ValidatedHosts = []
    for host in system_hosts:
        if not host.hostname:
            raise AutoconfPipelineError("Inventory contains a host without a hostname")
        merged_vars: HostVariables = inventory.export_merged_host_vars(host.hostname)

        try:
            MergedHostVars.model_validate(merged_vars)
        except ValidationError as exc:
            raise AutoconfPipelineError(
                f"Invalid system variables for {host.hostname} ({type(exc).__name__})"
            ) from exc
        validated_hosts.append((host.hostname, merged_vars))

    write_system_intermediates(
        inventory,
        autoconf_out,
        validated_hosts,
    )

    return inventory


def import_source_data(
    ansible_root: Path,
    autoconf_out: Path,
    subnet: str,
    system_group: str,
    logger: logging.Logger | None = None,
) -> AnsibleInventory:
    """Import configured Ansible sources into private Autoconf intermediates."""
    layout = AutoconfOutputLayout(autoconf_out)
    if logger is None:
        logger = get_logger(
            "autoconf_source_import",
            log_dir=layout.log_dir,
            reset=True,
        )

    log_heading(logger, "Import Autoconf source data")
    logger.info("Ansible root: %s", ansible_root)
    logger.info("Autoconf output: %s", autoconf_out)
    logger.info("Managed subnet: %s", subnet)
    logger.info("System inventory group: %s", system_group)
    autoconf_out.mkdir(parents=True, exist_ok=True)

    return build_system_merged_variables(
        ansible_root,
        autoconf_out,
        subnet,
        system_group,
        logger=logger,
    )
