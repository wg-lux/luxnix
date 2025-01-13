from pathlib import Path
import yaml
import configparser
from typing import List


def load_config(config_path: Path) -> dict:
    """Load a YAML configuration file from a given path"""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_hosts(hosts_path: Path) -> dict:
    """Load ansiblie hosts.ini file"""
    parser = configparser.ConfigParser(allow_no_value=True)
    parser.read(hosts_path)
    inventory = {}
    for section in parser.sections():
        inventory[section] = list(parser[section].keys())
    return inventory


def load_inventory(inventory_dir: Path) -> dict:
    """Load inventory from Ansible root directory"""
    assert inventory_dir.exists(), f"Inventory directory not found: {inventory_dir}"

    hosts_ini = inventory_dir / "hosts.ini"
    assert hosts_ini.exists(), f"Hosts file not found: {hosts_ini}"

    inventory = load_hosts(hosts_ini)

    return inventory


def _role_load_files(role: str, ansible_roles_dir: Path) -> List[Path]:
    """Load files from Ansible role directory"""
    files_dir = ansible_roles_dir / role / "files"
    files = []
    for file in files_dir.glob("*"):
        if file.is_file():
            files.append(file)
    return files


def _role_load_vars(role: str, ansible_roles_dir: Path) -> dict:
    """Load vars from Ansible role directory"""
    vars_dir = ansible_roles_dir / role / "vars"
    vars_file = vars_dir / "main.yml"
    role_vars = load_config(vars_file)
    return role_vars


def load_roles(ansible_roles_dir: Path) -> List[str]:
    """Load roles from Ansible roles directory"""
    roles = []
    for role in ansible_roles_dir.glob("*"):
        if role.is_dir():
            roles.append(role.name)

    roles = {
        role: {
            "files": _role_load_files(role, ansible_roles_dir),
            "vars": _role_load_vars(role, ansible_roles_dir),
        }
        for role in roles
    }
    return roles


def load_inventory_group_vars(ansible_inventory_dir: Path) -> dict:
    """Load inventory group from Ansible inventory directory"""
    group_vars_dir = ansible_inventory_dir / "group_vars"

    all_group_vars = {}
    for group_vars_file in group_vars_dir.glob("*"):
        group_vars = load_config(group_vars_file)
        all_group_vars[group_vars_file.stem] = group_vars

    return all_group_vars


def load_inventory_host_vars(ansible_inventory_dir: Path) -> dict:
    """Load inventory host from Ansible inventory directory"""
    host_vars_dir = ansible_inventory_dir / "host_vars"

    all_host_vars = {}
    for host_vars_file in host_vars_dir.glob("*"):
        host_vars = load_config(host_vars_file)
        all_host_vars[host_vars_file.stem] = host_vars

    return all_host_vars
