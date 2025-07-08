from pathlib import Path
from typing import List, Dict, Union
import yaml


# Base Load Config Utils
def _load_config(config_path: Path) -> dict:
    """Load a YAML configuration file from a given path"""
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)

    if not data:
        data = {}

    return data

def deep_update(dict1, dict2):
    dict1 = dict1.copy()
    dict2 = dict2.copy()

    for key, value in dict2.items():
        if isinstance(value, dict) and key in dict1 and isinstance(dict1[key], dict):
            dict1[key] = deep_update(dict1[key], value)
        else:
            dict1[key] = value

    return dict1

# Load Roles Utils
def _role_load_files(role: str, ansible_roles_dir: Path) -> List[Path]:
    """Load files from Ansible role directory"""
    files_dir = ansible_roles_dir / role / "files"
    files = []
    for file in files_dir.glob("*"):
        if file.is_file():
            files.append(file)
    return files

def _role_load_vars(role: str, ansible_roles_dir: Path, name: str) -> dict:
    """Load vars from Ansible role directory, also replaces the role name prefix with'role_'"""
    vars_dir = ansible_roles_dir / role / "vars"
    vars_file = vars_dir / "main.yml"
    role_vars = _load_config(vars_file)

    # remove prefix f"{name}_" from vars
    # Role Vars in ansible files should have the prefix of the role name
    # e.g. in roles/postgres_host_main/vars/main.yml we have
    # postgres_host_main_luxnix: {...} which should be converted to luxnix: {...}
    role_vars = {k.replace(f"{name}_", "role_"): v for k, v in role_vars.items()}

    return role_vars

def load_roles(ansible_roles_dir: Path) -> Dict[str, Union[List, Dict]]:
    """Load roles from Ansible roles directory"""
    _roles = []
    for role in ansible_roles_dir.glob("*"):
        if role.is_dir():
            _roles.append(role.name)

    roles = {
        role: {
            "files": _role_load_files(role, ansible_roles_dir),
            "vars": _role_load_vars(role, ansible_roles_dir, role),
        }
        for role in _roles
    }

    return roles

def load_roles_vars(ansible_roles_dir: Path) -> Dict[str, Dict]:
    """Load roles from Ansible roles directory"""
    roles = load_roles(ansible_roles_dir)
    roles_vars = {}
    for role, role_data in roles.items():
        roles_vars[role] = role_data["vars"]

    return roles_vars

def load_group_vars(group_vars_dir: Path) -> Dict[str, str]:
    group_vars = {}
    for group_vars_file in group_vars_dir.glob("*"):
        _group_vars = _load_config(group_vars_file)
        group_name = group_vars_file.stem
        group_vars[group_name] = _group_vars

    return group_vars

def load_host_vars(host_vars_dir: Path) -> Dict[str, dict]:
    host_vars: Dict[str, dict] = {}

    for host_vars_file in host_vars_dir.rglob("*.yml"):
        if host_vars_file.is_file():
            _host_vars = _load_config(host_vars_file)
            host_name = host_vars_file.stem

            #  Skip home-specific files for system
            if "host_vars/home" in str(host_vars_file):
                continue

            if host_name in host_vars:
                host_vars[host_name] = deep_update(host_vars[host_name], _host_vars)
            else:
                host_vars[host_name] = _host_vars

    return host_vars

def load_home_host_vars(ansible_inventory_dir: Path) -> Dict[str, dict]:
    from lx_administration.autoconf.imports.utils import _load_config, deep_update
    import pprint

    group_vars_dir = ansible_inventory_dir / "group_vars"
    host_vars_dir = ansible_inventory_dir / "host_vars" / "home"

    inventory_file = ansible_inventory_dir / "hosts.ini"

    import configparser
    parser = configparser.ConfigParser(allow_no_value=True, delimiters=('=',))
    parser.optionxform = str  # preserve case
    parser.read(inventory_file)

    group_membership = {}
    for section in parser.sections():
        for hostname in parser.options(section):
            group_membership.setdefault(hostname.strip(), set()).add(section.strip())

    # Step 1: load group vars into separate dicts
    all_group_vars = {}
    for file in group_vars_dir.glob("group_home_*.yml"):
        group_name = file.stem  # like group_home_editors
        group_data = _load_config(file)
        all_group_vars[group_name] = group_data

    home_host_vars: Dict[str, dict] = {}

    for host_file in host_vars_dir.glob("*.yml"):
        host_name = host_file.stem
        host_data = _load_config(host_file)

        merged = {}

        # Step 2: only merge in group vars where host is actually in that group
        for group_key, group_dict in all_group_vars.items():
            #if host_name in group_membership.get(group_key, set()):
            if group_key in group_membership.get(host_name, set()):
                merged = deep_update(merged, group_dict)

        # Step 3: merge in host-specific values
        merged = deep_update(merged, host_data)

        home_host_vars[host_name] = merged

        # DEBUG
        #print(f"[DEBUG] Final merged vars for {host_name}")
        #pprint.pprint(merged)

    return home_host_vars

def _dictkey_replace_underscore_keys(
    config_data: Dict[str, Union[List[str], str]], logger=None
) -> Dict[str, Union[List[str], str]]:
    from lx_administration.logging import get_logger

    transformed_config_data = {}
    if not logger:
        logger = get_logger("_dictkey_replace_underscore_keys")

    for nix_key, value in config_data.items():
        transformed_key = nix_key.replace("_", "-")
        if nix_key != transformed_key:
            logger.info(f"Transforming key {nix_key} to {transformed_key}")
            transformed_config_data[transformed_key] = value
        else:
            transformed_config_data[nix_key] = value

    return transformed_config_data


def is_home_only_host(host):
    """Returns True if host is ONLY for home configuration (not system)."""
    return (
        "home_config" in host.ansible_group_names and
        not any(g for g in host.ansible_group_names if not g.startswith("home_") and g != "home_config")
    )
#efined home-only detection logic in utils .py
#skips the export and YAML write for home-only hosts like abc@admin
#Return home_only_hosts list
#skips generating systems/x86_64-linux/<host>/default.nix.