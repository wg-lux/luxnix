import ipaddress
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from lx_administration.autoconf.imports.merge import ConfigMapping, deep_update
from lx_administration.autoconf.imports.sources import (
    load_group_vars as load_group_variable_sources,
)
from lx_administration.autoconf.imports.sources import (
    load_host_vars as load_host_variable_sources,
)
from lx_administration.autoconf.imports.sources import (
    load_roles as load_role_sources,
)
from lx_administration.autoconf.imports.sources import (
    load_roles_vars as load_role_variable_sources,
)
from lx_administration.logging import get_logger, log_heading
from lx_administration.yaml import (
    ansible_lint,
    dump_yaml,
    format_yaml,
    load_unique_yaml_file,
)

from ..config import DEFAULT_USERS
from .facts import AnsibleFactsModel


def _is_extra_user_attribute(attribute_name: str) -> bool:
    return attribute_name.startswith("extraUsers")


def _is_extra_user_name_attribute(attribute_name: str) -> bool:
    is_extra_user_attribute = _is_extra_user_attribute(attribute_name)
    if not is_extra_user_attribute:
        return False
    return attribute_name.endswith("name")


def _get_extra_user_names(vars: dict[str, Any]) -> list[str]:
    extra_user_names = []
    for key in vars.keys():
        if _is_extra_user_name_attribute(key):
            name = vars[key]
            assert isinstance(name, str), (
                f"Extra user name must be a string, got {name}"
            )
            extra_user_names.append(name)

    return extra_user_names


def _unique_names(names: list[str]) -> list[str]:
    """Remove duplicate names without changing their precedence order."""
    return list(dict.fromkeys(names))


def _membership_names(
    variables: ConfigMapping,
    option: str,
    source: str,
) -> list[str]:
    """Read one group or role membership list with a useful source error."""
    value = variables.get(option, [])
    if not isinstance(value, list) or any(not isinstance(name, str) for name in value):
        raise ValueError(f"{source} {option} must be a list of names")
    return value


class AnsibleInventoryHost(BaseModel):
    ansible_host: str | None = ""
    hostname: str | None
    ansible_group_names: list[str] = Field(default_factory=list)
    ansible_role_names: list[str] = Field(default_factory=list)
    extra_secret_names: list[str] = Field(default_factory=list)
    extra_user_names: list[str] = Field(default_factory=lambda: ["dev"])
    subnet: str | None = None
    vars: dict[str, Any] = Field(default_factory=dict)
    files: list[str] = Field(default_factory=list)
    facts: AnsibleFactsModel | None = None

    def get_extra_user_names(self) -> list[str]:
        extra_user_names = DEFAULT_USERS.copy()
        extra_user_names.extend(self.vars.get("os_extra_user_names", []))

        attribute_extra_user_names = _get_extra_user_names(self.vars)
        extra_user_names.extend(attribute_extra_user_names)

        return extra_user_names

    def validate_ansible_host(self):
        if not self.ansible_host:
            raise ValueError("ansible_host is required")

        if not self.subnet:
            raise ValueError("subnet is required")

        self.extra_user_names = self.get_extra_user_names()

        # make sure "all" is in ansible_group_names and is at first index, if not add it
        if "all" not in self.ansible_group_names:
            self.ansible_group_names.insert(0, "all")

        # check if ansible_host is in subnet
        if not self.ansible_host.startswith(self.subnet):
            raise ValueError(
                f"ansible_host {self.ansible_host} is not in subnet {self.subnet}"
            )

        extra_secret_names_val: Any = self.vars.get("extra_secret_names", [])
        if isinstance(extra_secret_names_val, list) and all(
            isinstance(_, str) for _ in extra_secret_names_val
        ):
            self.extra_secret_names = extra_secret_names_val
        else:
            self.extra_secret_names = []

    def update_facts(self, facts: AnsibleFactsModel):
        self.facts = facts

    def init_ansible_role_names(self):
        self.ansible_role_names = []

        existing_role_names = self.vars.get("ansible_roles", [])

        for _ in existing_role_names:
            assert isinstance(_, str), f"Role name must be a string, got {_}"

        self.ansible_role_names.extend(existing_role_names)


class AnsibleInventoryGroup(BaseModel):
    name: str
    vars: dict[str, Any] = Field(default_factory=dict)
    files: list[str] = Field(default_factory=list)
    extra_user_names: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_optional_fields(cls, values: dict[str, Any]):
        vars_val = values.get("vars")
        if vars_val is None:
            values["vars"] = {}
        elif isinstance(vars_val, dict):
            values["vars"] = {
                key: ({} if val is None else val) for key, val in vars_val.items()
            }
        files_val = values.get("files")
        if files_val is None:
            values["files"] = []
        extra_val = values.get("extra_user_names")
        if extra_val is None:
            values["extra_user_names"] = []
        return values

    def __str__(self):
        return super().__str__()

    def get_extra_user_names(self) -> list[str]:
        extra_user_names = _get_extra_user_names(self.vars)

        return extra_user_names

    def refresh_extra_user_names(self) -> None:
        self.extra_user_names = self.get_extra_user_names()


class AnsibleInventoryRole(BaseModel):
    name: str
    vars: dict[str, Any] | None = None
    files: list[str] = Field(default_factory=list)
    extra_user_names: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_optional_fields(cls, values: dict[str, Any]):
        if values.get("vars") is None:
            values["vars"] = {}
        elif isinstance(values["vars"], dict):
            values["vars"] = {
                key: ({} if val is None else val) for key, val in values["vars"].items()
            }
        if values.get("files") is None:
            values["files"] = []
        if values.get("extra_user_names") is None:
            values["extra_user_names"] = []
        return values

    @model_validator(mode="after")
    def _normalize_vars(self):
        if self.vars is None:
            self.vars = {}
        return self

    def get_extra_user_names(self) -> list[str]:
        if not self.vars:
            return []

        _vars = self.vars
        extra_user_names = _get_extra_user_names(_vars)

        return extra_user_names

    def refresh_extra_user_names(self) -> None:
        self.extra_user_names = self.get_extra_user_names()


class AnsibleInventory(BaseModel):
    groups: list[AnsibleInventoryGroup] = Field(default_factory=list)
    roles: list[AnsibleInventoryRole] = Field(default_factory=list)
    all: list[AnsibleInventoryHost] = Field(default_factory=list)
    file: str | None = None

    @classmethod
    def from_file(cls, filepath: str | Path) -> "AnsibleInventory":
        path_obj = Path(filepath)
        if not path_obj.is_file():
            raise FileNotFoundError(f"Inventory file not found: {path_obj}")

        return cls.model_validate(load_unique_yaml_file(path_obj))

    @classmethod
    def load_from_hosts_ini(cls, file: Path, subnet: str, logger=None):
        """Load inventory hosts using an explicitly configured address prefix."""
        try:
            if not subnet.endswith(".") or subnet.count(".") != 3:
                raise ValueError
            ipaddress.IPv4Address(f"{subnet}0")
        except (ipaddress.AddressValueError, ValueError) as exc:
            raise ValueError(
                "subnet must be a three-octet IPv4 prefix ending in '.'"
            ) from exc

        if logger is None:
            logger = get_logger("AnsibleInventory-load_from_file", reset=True)
        file = file.resolve()
        ansible_inventory_dir = file.parent
        ansible_root_dir = ansible_inventory_dir.parent
        inventory = cls(file=file.as_posix())
        inventory.load_host_vars(ansible_inventory_dir=ansible_inventory_dir)
        group_name: str | None = None
        with open(file) as f:
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
                    host = inventory.get_host_by_name(hostname)
                    assert host, f"No host found with name {hostname}"
                    host.subnet = subnet

                    # If no group header was seen yet, default to "all"
                    if group_name is None:
                        group_name = "all"
                        inventory.add_group_by_name(group_name)

                    inventory.add_group_to_host(hostname, group_name)

                    if len(parts) > 1 and parts[1].startswith("ansible_host="):
                        ip = parts[1].split("=")[1]
                        inventory.set_ansible_host_ip(hostname, ip)

        inventory.load_roles(ansible_root_dir)
        inventory.load_group_vars(ansible_inventory_dir)
        inventory.add_inventory_network_vars()
        inventory.load_role_vars(ansible_inventory_dir)

        log_heading(logger, f"Loaded Inventory from {file}")

        return inventory

    def get_role_names(self):
        return [role.name for role in self.roles]

    def get_hostnames(self):
        return [host.hostname for host in self.all]

    def get_group_names(self):
        return [group.name for group in self.groups]

    def get_all_extra_user_names(self):
        extra_user_names = []
        for host in self.all:
            host.validate_ansible_host()
            names = host.extra_user_names
            extra_user_names.extend(names)

        # add names from group vars
        for group in self.groups:
            group.refresh_extra_user_names()
            names = group.extra_user_names
            extra_user_names.extend(names)

        # add names from role_vars
        for role in self.roles:
            role.refresh_extra_user_names()
            names = role.extra_user_names
            extra_user_names.extend(names)

        return extra_user_names

    def _expand_membership_names(
        self,
        group_names: list[str],
        role_names: list[str],
    ) -> tuple[list[str], list[str]]:
        """Resolve transitive group and role memberships in precedence order."""
        expanded_groups = _unique_names(group_names)
        expanded_roles = _unique_names(role_names)

        while True:
            discovered_groups = list(expanded_groups)
            discovered_roles = list(expanded_roles)

            for current_group_name in expanded_groups:
                variables = self.get_group_by_name(current_group_name).vars
                source = f"group {current_group_name}"
                discovered_groups.extend(
                    _membership_names(variables, "ansible_groups", source)
                )
                discovered_roles.extend(
                    _membership_names(variables, "ansible_roles", source)
                )

            for current_role_name in expanded_roles:
                variables = self.get_role_by_name(current_role_name).vars or {}
                source = f"role {current_role_name}"
                discovered_groups.extend(
                    _membership_names(variables, "ansible_groups", source)
                )
                discovered_roles.extend(
                    _membership_names(variables, "ansible_roles", source)
                )

            next_groups = _unique_names(discovered_groups)
            next_roles = _unique_names(discovered_roles)
            if next_groups == expanded_groups and next_roles == expanded_roles:
                return expanded_groups, expanded_roles

            expanded_groups = next_groups
            expanded_roles = next_roles

    def export_merged_host_vars(self, hostname: str) -> ConfigMapping:
        host = self.get_host_by_name(hostname)
        assert host, f"No host found with name {hostname}"

        group_names, role_names = self._expand_membership_names(
            host.ansible_group_names,
            host.ansible_role_names,
        )

        group_vars: ConfigMapping = {}
        for group_name in group_names:
            group = self.get_group_by_name(group_name)
            group_vars = deep_update(group_vars, group.vars)

        role_vars: ConfigMapping = {}
        for role_name in role_names:
            role = self.get_role_by_name(role_name)
            role_vars = deep_update(role_vars, role.vars or {})

        merged_vars = deep_update(group_vars, role_vars)
        merged_vars = deep_update(merged_vars, host.vars)

        return merged_vars

    def validate_inventory(self) -> None:
        for group in self.groups:
            group.refresh_extra_user_names()

        for role in self.roles:
            role.refresh_extra_user_names()

        for host in self.all:
            host.validate_ansible_host()

    def save_to_file(
        self,
        inventory_file: Path,
        *,
        directory_mode: int | None = None,
        file_mode: int | None = None,
    ):
        self.validate_inventory()
        dump_yaml(
            self.model_dump(mode="python"),
            inventory_file,
            format_func=format_yaml,
            lint_func=ansible_lint,
            directory_mode=directory_mode,
            file_mode=file_mode,
        )

    def hostname_update_ansible_facts(self, hostname: str, facts: AnsibleFactsModel):
        host = self.get_host_by_name(hostname)
        assert host, f"No host found with name {hostname}"
        host.update_facts(facts)

    def group_name_exists(self, group_name: str) -> bool:
        return any(group.name == group_name for group in self.groups)

    def role_name_exists(self, role_name: str) -> bool:
        return any(role.name == role_name for role in self.roles)

    def get_group_by_name(self, group_name: str, logger=None) -> AnsibleInventoryGroup:
        """Return the exact group, creating it when it is not loaded yet."""
        if logger is None:
            logger = get_logger("AnsibleInventory-get_group_by_name", reset=True)
        matches = [group for group in self.groups if group.name == group_name]
        if len(matches) > 1:
            raise ValueError(f"Multiple groups found with name {group_name}")
        if matches:
            return matches[0]

        logger.warning("No group found with name %s; adding it", group_name)
        group = AnsibleInventoryGroup(name=group_name)
        self.groups.append(group)
        return group

    def get_role_by_name(self, role_name: str, logger=None) -> AnsibleInventoryRole:
        """Return the exact role, creating it when it is not loaded yet."""
        if logger is None:
            logger = get_logger("AnsibleInventory-get_role_by_name", reset=True)
        matches = [role for role in self.roles if role.name == role_name]
        if len(matches) > 1:
            raise ValueError(f"Multiple roles found with name {role_name}")
        if matches:
            return matches[0]

        logger.warning("No role found with name %s; adding it", role_name)
        role = AnsibleInventoryRole(name=role_name)
        self.roles.append(role)
        return role

    def host_name_exists(self, host_name: str):
        _host = [_ for _ in self.all if _.hostname == host_name]
        return bool(_host)

    def add_group_by_name(self, group_name: str):
        if not self.group_name_exists(group_name):
            self.groups.append(AnsibleInventoryGroup(name=group_name))

    def add_role_by_name(self, role_name: str):
        if not self.role_name_exists(role_name):
            self.roles.append(AnsibleInventoryRole(name=role_name))

    def add_host_by_name(self, hostname: str):
        if not self.host_name_exists(hostname):
            self.all.append(AnsibleInventoryHost(hostname=hostname))

    def host_exists(self, ansible_host: str):
        return any(host.ansible_host == ansible_host for host in self.all)

    def get_host(self, ansible_host: str):
        if not self.host_exists(ansible_host):
            raise ValueError(f"No host found with name {ansible_host}")

        host = [_ for _ in self.all if _.ansible_host == ansible_host]
        assert len(host) == 1, f"Multiple hosts found with name {ansible_host}"
        return host[0]

    def get_host_by_name(self, host_name: str) -> AnsibleInventoryHost | None:
        host = [_ for _ in self.all if _.hostname == host_name]
        if host:
            assert len(host) == 1, f"Multiple hosts found with name {host_name}"
            return host[0]
        logger = get_logger("AnsibleInventory-get_host_by_name", reset=True)
        # ValueError(f"No host found with name {host_name}")
        logger.warning(f"No host found with name {host_name}, adding")

        return None

    def set_ansible_host_ip(self, hostname: str, ansible_host: str):
        host = self.get_host_by_name(hostname)
        assert host, f"No host found with name {hostname}"
        host.ansible_host = ansible_host
        host.validate_ansible_host()

    def add_group_to_host(self, host_name: str, group_name: str):
        host = self.get_host_by_name(host_name)
        assert host, f"No host found with name {host_name}"
        host.ansible_group_names.append(group_name)
        host.ansible_group_names = _unique_names(host.ansible_group_names)

    def add_role_to_host(self, host_name: str, role_name: str):
        host = self.get_host_by_name(host_name)
        assert host, f"No host found with name {host_name}"
        host.ansible_role_names.append(role_name)
        host.ansible_role_names = _unique_names(host.ansible_role_names)

    def load_roles(self, ansible_root_dir: Path):
        roles_dir = ansible_root_dir / "roles"

        _roles = load_role_sources(roles_dir)
        roles: list[AnsibleInventoryRole] = []
        for role, value in _roles.items():
            if isinstance(value, dict):
                files_list = value.get("files", [])
                vars_dict = value.get("vars", {})
            else:
                files_list = []
                vars_dict = {}
            files_as_str = [str(p) for p in files_list]
            roles.append(
                AnsibleInventoryRole(name=role, files=files_as_str, vars=vars_dict)
            )

        self.roles = roles

    def load_role_vars(self, ansible_inventory_dir: Path):
        role_vars_dir = ansible_inventory_dir / "role_vars"

        role_vars = load_role_variable_sources(role_vars_dir)

        for role_name, vars in role_vars.items():
            role = self.get_role_by_name(role_name)
            assert isinstance(vars, dict)
            role.vars = deep_update(role.vars or {}, vars)

    def load_group_vars(self, ansible_inventory_dir: Path):
        group_vars_dir = ansible_inventory_dir / "group_vars"

        group_vars = load_group_variable_sources(group_vars_dir)

        for group_name, vars in group_vars.items():
            group = self.get_group_by_name(group_name)
            assert isinstance(vars, dict)
            group.vars = deep_update(group.vars, vars)

    def add_inventory_network_vars(self) -> None:
        """Expose canonical inventory addresses as generated LuxNix options."""
        all_group = self.get_group_by_name("all")
        group_luxnix = all_group.vars.setdefault("group_luxnix", {})
        if not isinstance(group_luxnix, dict):
            raise ValueError("all.group_luxnix must be a mapping")

        derived = {
            (
                "generic_settings.network.hosts."
                f"{host.hostname.replace('-', '_')}.ip_vpn"
            ): f'"{host.ansible_host}"'
            for host in self.all
            if host.hostname and host.ansible_host
        }
        duplicates = set(group_luxnix) & set(derived)
        if duplicates:
            names = ", ".join(sorted(duplicates))
            raise ValueError(
                "VPN host addresses are derived from hosts.ini; "
                f"remove duplicate group variables: {names}"
            )
        group_luxnix.update(derived)

    def load_host_vars(self, ansible_inventory_dir: Path):
        host_vars_dir = ansible_inventory_dir / "host_vars"

        host_vars = load_host_variable_sources(host_vars_dir)

        for host_name, vars in host_vars.items():
            host = self.get_host_by_name(host_name)
            if not host:
                host = AnsibleInventoryHost(
                    hostname=host_name, extra_user_names=["root", "center-user"]
                )
                self.all.append(host)
            assert isinstance(vars, dict)

            host.vars = deep_update(host.vars, vars)
