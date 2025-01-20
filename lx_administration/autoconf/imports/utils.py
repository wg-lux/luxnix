from pathlib import Path
from typing import List, Dict, Union
import yaml


# Base Load Config Utils
def _load_config(config_path: Path) -> dict:
    """Load a YAML configuration file from a given path"""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def ansible_lint_and_format(file: Path):
    import subprocess
    from ruamel.yaml import YAML

    yaml_parser = YAML()
    with open(file, "r") as fr:
        data = yaml_parser.load(fr)

    yaml_parser.indent(mapping=2, sequence=4, offset=2)
    with open(file, "w") as fw:
        yaml_parser.dump(data, fw)

    subprocess.run(["ansible-lint", file])


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


def _role_load_vars(role: str, ansible_roles_dir: Path) -> dict:
    """Load vars from Ansible role directory"""
    vars_dir = ansible_roles_dir / role / "vars"
    vars_file = vars_dir / "main.yml"
    role_vars = _load_config(vars_file)
    return role_vars


def load_roles(ansible_roles_dir: Path) -> Dict[str, Union[List, Dict]]:
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


def load_group_vars(group_vars_dir: Path) -> Dict[str, str]:
    group_vars = {}
    for group_vars_file in group_vars_dir.glob("*"):
        _group_vars = _load_config(group_vars_file)
        group_name = group_vars_file.stem
        group_vars[group_name] = _group_vars

    return group_vars


def load_host_vars(host_vars_dir: Path) -> Dict[str, str]:
    host_vars = {}
    for host_vars_file in host_vars_dir.glob("*"):
        _host_vars = _load_config(host_vars_file)
        host_name = host_vars_file.stem
        host_vars[host_name] = _host_vars

    return host_vars
