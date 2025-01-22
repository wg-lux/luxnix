from pydantic import BaseModel
from typing import Dict, List, Optional, Union
from pathlib import Path
from lx_administration.logging import log_heading, get_logger  #
from .facts import AnsibleFactsModel
from lx_administration.models.ansible.merged_host_vars import MergedHostVars
from lx_administration.yaml import dump_yaml, ansible_lint, format_yaml


class AnsibleInventoryHost(BaseModel):
    ansible_host: Optional[str] = ""
    hostname: Optional[str]
    ansible_group_names: List[str] = []
    ansible_role_names: List[str] = []
    subnet: Optional[str] = "172.16.255."
    vars: Dict[str, Union[str, Dict, List[str]]] = {}
    files: List[str] = []
    facts: Optional[AnsibleFactsModel] = None

    def _order_group_names(self):
        # TODO harden
        # make sure "all" is in ansible_group_names and is at first index, if not add it
        if "all" not in self.ansible_group_names:
            self.ansible_group_names.insert(0, "all")

        # make sure that "openvpn_host" is last if it is in ansible_group_names
        if "openvpn_host" in self.ansible_group_names:
            self.ansible_group_names.remove("openvpn_host")
            self.ansible_group_names.append("openvpn_host")

    def validate_ansible_host(self):
        if not self.ansible_host:
            raise ValueError("ansible_host is required")

        if not self.subnet:
            raise ValueError("subnet is required")

        # make sure "all" is in ansible_group_names and is at first index, if not add it
        if "all" not in self.ansible_group_names:
            self.ansible_group_names.insert(0, "all")

        # check if ansible_host is in subnet
        if not self.ansible_host.startswith(self.subnet):
            raise ValueError(
                f"ansible_host {self.ansible_host} is not in subnet {self.subnet}"
            )

    def update_facts(self, facts: AnsibleFactsModel):
        self.facts = facts


class AnsibleInventoryGroup(BaseModel):
    name: str
    vars: Dict[str, Union[str, Dict, List[str]]] = {}
    files: List[str] = []

    def __str__(self):
        return super().__str__()


class AnsibleInventoryRole(BaseModel):
    name: str
    vars: Dict[str, Union[str, Dict, List[str]]] = {}
    files: List[str] = []


class AnsibleInventory(BaseModel):
    groups: List[AnsibleInventoryGroup] = []
    roles: List[AnsibleInventoryRole] = []
    all: List[AnsibleInventoryHost] = []
    file: str = "./ansible/inventory/hosts.ini"

    @classmethod
    def from_file(cls, filepath: str):
        import yaml

        filepath = Path(filepath)
        assert filepath.exists(), f"File not found: {filepath}"

        with open(filepath, "r") as f:
            data = yaml.load(f, yaml.SafeLoader)

            inventory = cls.model_validate(data)

        return inventory

    # Create Class Method to load inventory from file
    @classmethod
    def load_from_hosts_ini(cls, file: Path, subnet: str = "172.16.255."):
        logger = get_logger("AnsibleInventory-load_from_file", reset=True)

        # assert subnet is ip address with missing last octet
        assert subnet.endswith(".") and len(subnet.split(".")) == 4
        # Initialize temporary dict to read inventory
        inventory = cls(file=file.resolve().as_posix())
        with open(file, "r") as f:
            for raw_line in f:
                line = raw_line.strip()

                if not line or line.startswith(";") or line.startswith("#"):
                    continue

                if line.startswith("[") and line.endswith("]"):
                    group_name = line[1:-1]
                    inventory.add_group_by_name(group_name)
                    continue

                parts = line.split()

                if parts:
                    hostname = parts[0]
                    assert hostname, "hostname is required"
                    inventory.add_host_by_name(hostname)
                    inventory.add_group_to_host(hostname, group_name)

                    if len(parts) > 1 and parts[1].startswith("ansible_host="):
                        ip = parts[1].split("=")[1]
                        inventory.set_ansible_host_ip(hostname, ip)

        inventory.load_roles(file.parent)
        inventory.load_group_vars(file.parent)

        log_heading(logger, f"Loaded Inventory from {file}")

        return inventory

    def get_role_names(self):
        return [role.name for role in self.roles]

    def get_hostnames(self):
        return [host.hostname for host in self.all]

    def get_group_names(self):
        return [group.name for group in self.groups]

    def export_merged_host_vars(self, hostname: str) -> Dict:
        from lx_administration.autoconf.imports.utils import deep_update

        # self.update_hosts_group_vars()
        host = self.get_host_by_name(hostname)

        group_names = host.ansible_group_names

        _check_again = True

        while _check_again:
            _check_again = False
            new_group_names = []
            for group_name in group_names:
                group = self.get_group_by_name(group_name)
                _new_group_names = group.vars.get("ansible_groups", [])

                for group_name in _new_group_names:
                    if group_name not in group_names:
                        new_group_names.append(group_name)
                        _check_again = True

                if _check_again:
                    group_names = group_names + new_group_names

        group_vars = {}
        for group_name in group_names:
            group = self.get_group_by_name(group_name)
            group_vars = deep_update(group_vars, group.vars)

        merged_vars = deep_update(group_vars, host.vars)

        return merged_vars

    def save_to_file(self, inventory_file: Path = Path("./autoconf/inventory.yml")):
        dump_yaml(
            self.model_dump(mode="python"),
            inventory_file,
            format_func=format_yaml,
            lint_func=ansible_lint,
        )

    def hostname_update_ansible_facts(self, hostname: str, facts: AnsibleFactsModel):
        self.get_host_by_name(hostname).update_facts(facts)

    def group_name_exists(self, group_name: str):
        return any(group_name in group.name for group in self.groups)

    def get_group_by_name(self, group_name: str, logger=None):
        if not logger:
            logger = get_logger("AnsibleInventory-get_group_by_name", reset=True)
        group = [_ for _ in self.groups if _.name == group_name]
        if group:
            assert len(group) == 1, f"Multiple groups found with name {group_name}"
            return group[0]

        else:
            logger.warning(f"No group found with name {group_name}, adding")
            self.add_group_by_name(group_name)
            group = self.get_group_by_name(group_name)
            return group

    def host_name_exists(self, host_name: str):
        _host = [_ for _ in self.all if _.hostname == host_name]
        return bool(_host)

    def add_group_by_name(self, group_name: str):
        if not self.group_name_exists(group_name):
            self.groups.append(AnsibleInventoryGroup(name=group_name))

    def add_host_by_name(self, hostname: str):
        if not self.host_name_exists(hostname):
            self.all.append(AnsibleInventoryHost(hostname=hostname))

    def host_exists(self, ansible_host: str):
        return any(ansible_host in host.ansible_host for host in self.all)

    def get_host(self, ansible_host: str):
        if not self.host_exists(ansible_host):
            raise ValueError(f"No host found with name {ansible_host}")

        host = [_ for _ in self.all if _.ansible_host == ansible_host]
        assert len(host) == 1, f"Multiple hosts found with name {ansible_host}"
        return host[0]

    def get_host_by_name(self, host_name: str):
        host = [_ for _ in self.all if _.hostname == host_name]
        if host:
            assert len(host) == 1, f"Multiple hosts found with name {host_name}"
            return host[0]

        raise ValueError(f"No host found with name {host_name}")

    def set_ansible_host_ip(self, hostname: str, ansible_host: str):
        host = self.get_host_by_name(hostname)
        host.ansible_host = ansible_host
        host.validate_ansible_host()

    def add_group_to_host(self, host_name: str, group_name: str):
        host = self.get_host_by_name(host_name)
        host.ansible_group_names.append(group_name)
        host.ansible_group_names = list(set(host.ansible_group_names))

    def load_roles(self, ansible_inventory_dir: Path):
        from lx_administration.autoconf.imports.utils import load_roles

        roles_dir = ansible_inventory_dir / "roles"

        roles = load_roles(roles_dir)
        roles = [
            AnsibleInventoryRole(name=role, **roles[role])
            for role, value in roles.items()
        ]

        self.roles = roles

    def load_group_vars(self, ansible_inventory_dir: Path):
        from lx_administration.autoconf.imports.utils import (
            load_group_vars,
            deep_update,
        )

        group_vars_dir = ansible_inventory_dir / "group_vars"

        group_vars = load_group_vars(group_vars_dir)

        for group_name, vars in group_vars.items():
            # print("--" * 10)
            # print(group_name)
            # print(vars)
            # print("--" * 10)
            group = self.get_group_by_name(group_name)
            assert isinstance(vars, dict)
            group.vars = deep_update(group.vars, vars)

    def load_host_vars(self, ansible_inventory_dir: Path):
        from lx_administration.autoconf.imports.utils import load_host_vars, deep_update
        # from lx_administration.models.ansible import AnsibleInventoryHost

        host_vars_dir = ansible_inventory_dir / "host_vars"

        host_vars = load_host_vars(host_vars_dir)

        for host_name, vars in host_vars.items():
            host = self.get_host_by_name(host_name)
            assert isinstance(vars, dict)
            host.vars = deep_update(host.vars, vars)

    def build_merged_vars(self, hostname: str) -> MergedHostVars:
        merged_data = self.export_merged_host_vars(hostname)
        return MergedHostVars(
            group_luxnix=merged_data.get("group_luxnix", {}),
            group_roles=merged_data.get("group_roles", {}),
            group_services=merged_data.get("group_services", {}),
            host_luxnix=merged_data.get("host_luxnix", {}),
            host_roles=merged_data.get("host_roles", {}),
            host_services=merged_data.get("host_services", {}),
        )
