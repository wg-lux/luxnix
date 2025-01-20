from pathlib import Path
import yaml
import configparser
from typing import List


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
