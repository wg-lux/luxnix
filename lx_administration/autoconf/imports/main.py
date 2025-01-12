from pathlib import Path
import yaml
from . import (
    load_all_host_facts,
    load_inventory,
    load_roles,
    load_inventory_group_vars,
    load_inventory_host_vars,
)
from .host_configs import get_host_configs
import warnings
import pprint


from lx_administration.logging import log_heading, get_logger


def deep_update(dict1, dict2):
    dict1 = dict1.copy()
    dict2 = dict2.copy()

    for key, value in dict2.items():
        if isinstance(value, dict) and key in dict1 and isinstance(dict1[key], dict):
            dict1 = deep_update(dict1[key], value)
        else:
            dict1[key] = value

    return dict1


def dump_config(
    autoconf_out: Path,
    inventory: dict,
    host_configs: dict,
    roles: dict,
    group_vars: dict,
    host_vars: dict,
    logger=None,
):
    if not logger:
        logger = get_logger("dump_config")

    with open(autoconf_out / "inventory.yml", "w") as f:
        yaml.dump(
            inventory, f, Dumper=IndentedDumper, default_flow_style=False, indent=2
        )
        logger.info(f"Saved inventory to {autoconf_out / 'inventory.yml'}")

    with open(autoconf_out / "host_configs.yml", "w") as f:
        yaml.dump(
            host_configs, f, Dumper=IndentedDumper, default_flow_style=False, indent=2
        )
        logger.info(f"Saved host configs to {autoconf_out / 'host_configs.yml'}")

    with open(autoconf_out / "roles.yml", "w") as f:
        yaml.dump(roles, f, Dumper=IndentedDumper, default_flow_style=False, indent=2)
        logger.info(f"Saved roles to {autoconf_out / 'roles.yml'}")

    with open(autoconf_out / "group_vars.yml", "w") as f:
        yaml.dump(
            group_vars, f, Dumper=IndentedDumper, default_flow_style=False, indent=2
        )
        logger.info(f"Saved group vars to {autoconf_out / 'group_vars.yml'}")

    with open(autoconf_out / "host_vars.yml", "w") as f:
        yaml.dump(
            host_vars, f, Dumper=IndentedDumper, default_flow_style=False, indent=2
        )
        logger.info(f"Saved host vars to {autoconf_out / 'host_vars.yml'}")


def warn_if_overridden(key, group, _conf, host, logger=None, verbose=False):
    if logger:
        logger.warning(
            f"Host var '{key}' overridden for host '{host}' in group '{group}'"
        )

    if key in _conf and verbose:
        warnings.warn(
            f"Host var '{key}' overridden for host '{host}' in group '{group}'"
        )


def merge_host_group_vars(host_configs, host, group, group_vars, logger=None):
    # DEBUG
    verbose = False

    if not logger:
        logger = get_logger("merge_host_group_vars")

    if verbose:
        print("------------merge_host_group_vars------------")
        print(f"host: {host}, group: {group}")
        print(f"group_vars[{group}]:")
        pp = pprint.PrettyPrinter(indent=2)
        if group in group_vars:
            pp.pprint(group_vars[group])
        else:
            print(f"No group_vars found for group '{group}'")

    _group_config: dict = group_vars.get(group, {})

    # make deep copy
    _group_config = _group_config.copy()

    _group_roles = _group_config.pop("group_roles", {})
    _group_services = _group_config.pop("group_services", {})
    _group_luxnix = _group_config.pop("group_luxnix", {})

    host_configs[host]["group_vars"][group] = _group_config

    for key, value in _group_roles.items():
        warn_if_overridden(key, group, host_configs[host]["role_configs"], host)
        host_configs[host]["role_configs"][key] = value

    for key, value in _group_luxnix.items():
        warn_if_overridden(key, group, host_configs[host]["luxnix_configs"], host)
        host_configs[host]["luxnix_configs"][key] = value

    for key, value in _group_services.items():
        warn_if_overridden(key, group, host_configs[host]["service_configs"], host)
        host_configs[host]["service_configs"][key] = value


def merge_host_vars(host_config, host_vars):
    # make deep copy of host_config
    verbose = False

    host_config = host_config.copy()
    host_vars = host_vars.copy()

    assert_keys = ["role_configs", "service_configs", "luxnix_configs"]
    for key in assert_keys:
        if key not in host_config:
            host_config[key] = {}

    if verbose:
        print("------------merge_host_vars------------")
        pp = pprint.PrettyPrinter(indent=2)
        print("host_config:")
        pp.pprint(host_config)

        print("\n\nhost_vars:")
        pp.pprint(host_vars)

    _host_roles = host_vars.pop("host_roles", {})
    _host_services = host_vars.pop("host_services", {})
    _host_luxnix = host_vars.pop("host_luxnix", {})

    # merge dicts
    if verbose:
        print("Merging host_vars with host_config")

    host_config["role_configs"] = deep_update(host_config["role_configs"], _host_roles)
    host_config["service_configs"] = deep_update(
        host_config["service_configs"], _host_services
    )
    host_config["luxnix_configs"] = deep_update(
        host_config["luxnix_configs"], _host_luxnix
    )

    return host_config


class IndentedDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(IndentedDumper, self).increase_indent(flow, False)


def ansible_etl(ansible_root: Path, autoconf_out: Path, subnet: str, logger=None):
    if not logger:
        logger = get_logger("ansible_etl", reset=True)

    ansible_inventory_dir = ansible_root / "inventory"
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

    host_facts = load_all_host_facts(host_facts_dir)

    with open(autoconf_out / "host_facts.yml", "w") as f:
        yaml.safe_dump(host_facts, f)
        logger.info(f"Saved host facts to {autoconf_out / 'host_facts.yml'}")

    inventory = load_inventory(ansible_inventory_dir)
    host_configs = get_host_configs(host_facts, inventory, subnet)
    roles = load_roles(ansible_root / "roles")
    group_vars = load_inventory_group_vars(ansible_inventory_dir)
    host_vars = load_inventory_host_vars(ansible_inventory_dir)

    return host_facts, inventory, host_configs, roles, group_vars, host_vars


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

    # Load inventory
    host_facts, inventory, host_configs, roles, group_vars, host_vars = ansible_etl(
        ansible_root, autoconf_out, subnet, logger
    )

    for host, host_config in host_configs.items():
        host_configs[host]["role_configs"] = {}
        host_configs[host]["service_configs"] = {}
        host_configs[host]["luxnix_configs"] = {}

        host_configs[host]["group_vars"] = {}

        merge_host_group_vars(host_configs, host, "all", group_vars, logger=logger)

        for _group, _group_hosts in inventory.items():
            if host in _group_hosts:
                merge_host_group_vars(
                    host_configs, host, _group, group_vars, logger=logger
                )

        merged_config = merge_host_vars(host_config, host_vars[host])
        merged_config["host_vars"] = host_vars[host]
        host_configs[host] = merged_config

    dump_config(
        autoconf_out,
        inventory,
        host_configs,
        roles,
        group_vars,
        host_vars,
        logger=logger,
    )

    return host_facts, inventory, host_configs, roles, group_vars, host_vars
