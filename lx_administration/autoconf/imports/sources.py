"""Load Ansible variable sources for the Autoconf import pipeline."""

from pathlib import Path
from typing import TypedDict, cast

import yaml

from lx_administration.yaml import load_unique_yaml_file

from ..errors import (
    AutoconfSourceError,
    AutoconfSourceNotFoundError,
    AutoconfYamlError,
)
from ..layout import AnsibleInventoryLayout
from .merge import ConfigMapping, deep_update, require_string_mapping

YAML_SUFFIXES = frozenset({".yml", ".yaml"})


class RoleData(TypedDict):
    """Files and variables loaded for one Ansible role."""

    files: list[Path]
    vars: ConfigMapping


def _yaml_files(
    directory: Path,
    *,
    pattern: str = "*",
    recursive: bool = False,
) -> list[Path]:
    """Return regular YAML files in deterministic path order."""
    candidates = directory.rglob(pattern) if recursive else directory.glob(pattern)
    return sorted(
        path
        for path in candidates
        if path.is_file() and path.suffix in YAML_SUFFIXES
    )


def _yaml_files_by_stem(
    files: list[Path],
    *,
    source: str,
) -> dict[str, Path]:
    """Index YAML files by logical name and reject ambiguous suffix variants."""
    indexed: dict[str, Path] = {}
    for path in files:
        if previous := indexed.get(path.stem):
            raise AutoconfSourceError(
                f"Ambiguous {source} YAML source for '{path.stem}': "
                f"{previous} and {path}"
            )
        indexed[path.stem] = path
    return indexed


def _string_list(value: object, error_message: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AutoconfSourceError(error_message)
    return cast("list[str]", value)


def _load_config(config_path: Path) -> ConfigMapping:
    """Load one YAML mapping, treating an empty file as an empty mapping."""
    if not config_path.is_file():
        raise AutoconfSourceNotFoundError(
            f"Autoconf YAML source not found: {config_path}"
        )
    try:
        data = load_unique_yaml_file(config_path)
    except yaml.YAMLError as error:
        detail = ""
        if isinstance(error, yaml.constructor.ConstructorError) and str(
            error.problem
        ).startswith("found duplicate key"):
            detail = f": {error.problem}"
        raise AutoconfYamlError(f"Invalid YAML in {config_path}{detail}") from error
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise AutoconfSourceError(f"Expected a YAML mapping in {config_path}")
    if any(not isinstance(key, str) for key in data):
        raise AutoconfSourceError(f"Expected string keys in YAML mapping {config_path}")
    return cast("ConfigMapping", data)


def _role_load_files(role: str, ansible_roles_dir: Path) -> list[Path]:
    """Return regular files supplied by an Ansible role in stable order."""
    files_dir = ansible_roles_dir / role / "files"
    if not files_dir.is_dir():
        return []
    return sorted(path for path in files_dir.iterdir() if path.is_file())


def _normalize_role_var_name(role: str, name: str) -> str:
    """Replace a role-specific prefix without altering later occurrences."""
    prefix = f"{role}_"
    if name.startswith(prefix):
        return f"role_{name.removeprefix(prefix)}"
    return name


def _role_load_vars(
    role: str,
    ansible_roles_dir: Path,
) -> ConfigMapping:
    """Load optional role vars and normalize their role-specific prefix."""
    vars_dir = ansible_roles_dir / role / "vars"
    vars_files = [path for path in _yaml_files(vars_dir) if path.stem == "main"]
    if not vars_files:
        return {}
    vars_file = _yaml_files_by_stem(
        vars_files,
        source=f"role '{role}' variables",
    )["main"]
    role_vars = _load_config(vars_file)
    return {
        _normalize_role_var_name(role, key): value
        for key, value in role_vars.items()
    }


def load_roles(ansible_roles_dir: Path) -> dict[str, RoleData]:
    """Load role files and variables in stable role-name order."""
    if not ansible_roles_dir.is_dir():
        return {}

    role_names = sorted(
        path.name for path in ansible_roles_dir.iterdir() if path.is_dir()
    )
    return {
        role: {
            "files": _role_load_files(role, ansible_roles_dir),
            "vars": _role_load_vars(role, ansible_roles_dir),
        }
        for role in role_names
    }


def load_roles_vars(ansible_roles_dir: Path) -> dict[str, ConfigMapping]:
    """Return only the variable mapping for each loaded role."""
    roles_vars: dict[str, ConfigMapping] = {}
    for role, role_data in load_roles(ansible_roles_dir).items():
        roles_vars[role] = role_data["vars"]
    return roles_vars


def load_group_vars(group_vars_dir: Path) -> dict[str, ConfigMapping]:
    """Load group files or split group directories in stable filename order."""
    if not group_vars_dir.is_dir():
        return {}

    group_files = {
        name: _load_config(path)
        for name, path in _yaml_files_by_stem(
            _yaml_files(group_vars_dir),
            source="group variables",
        ).items()
    }
    group_directories = {
        path.name: path for path in sorted(group_vars_dir.iterdir()) if path.is_dir()
    }
    duplicate_sources = set(group_files) & set(group_directories)
    if duplicate_sources:
        names = ", ".join(sorted(duplicate_sources))
        raise AutoconfSourceError(
            f"group vars have both file and directory sources: {names}"
        )

    for group_name, directory in group_directories.items():
        merged: ConfigMapping = {}
        split_files = _yaml_files_by_stem(
            _yaml_files(directory),
            source=f"group '{group_name}' variables",
        )
        for path in split_files.values():
            merged = deep_update(merged, _load_config(path))
        group_files[group_name] = merged
    return group_files


def load_host_vars(host_vars_dir: Path) -> dict[str, ConfigMapping]:
    """Load system host vars, excluding the dedicated home subtree."""
    host_vars: dict[str, ConfigMapping] = {}
    if not host_vars_dir.is_dir():
        return host_vars

    home_vars_dir = host_vars_dir / "home"
    source_files = [
        path
        for path in _yaml_files(host_vars_dir, recursive=True)
        if home_vars_dir not in path.parents
    ]
    for hostname, host_vars_file in _yaml_files_by_stem(
        source_files,
        source="host variables",
    ).items():
        variables = _load_config(host_vars_file)
        host_vars[hostname] = variables
    return host_vars


def load_home_host_vars(ansible_inventory_dir: Path) -> dict[str, ConfigMapping]:
    """Merge configured home-group vars with each home host's own vars.

    Group files are applied in filename order; a later group and then the host
    file override earlier values.
    """
    layout = AnsibleInventoryLayout(ansible_inventory_dir)
    home_hosts_config = _load_config(layout.home_manifest)
    if home_hosts_config.get("schema_version") != 1:
        raise AutoconfSourceError("home-hosts.yml must use schema_version 1")

    default_groups = _string_list(
        home_hosts_config.get("default_groups", []),
        "home-hosts.yml default_groups must be a list of names",
    )
    configured_hosts = require_string_mapping(
        home_hosts_config.get("hosts", {}),
        "home-hosts.yml hosts",
    )

    group_vars = {
        name: _load_config(path)
        for name, path in _yaml_files_by_stem(
            _yaml_files(layout.group_vars_dir, pattern="group_home_*") ,
            source="home group variables",
        ).items()
    }
    unknown_defaults = set(default_groups) - set(group_vars)
    if unknown_defaults:
        names = ", ".join(sorted(unknown_defaults))
        raise AutoconfSourceError(f"home-hosts.yml references unknown groups: {names}")

    host_files = _yaml_files_by_stem(
        _yaml_files(layout.home_vars_dir),
        source="home host variables",
    )
    if set(configured_hosts) != set(host_files):
        missing_config = set(host_files) - set(configured_hosts)
        missing_files = set(configured_hosts) - set(host_files)
        details = []
        if missing_config:
            details.append(f"missing config: {', '.join(sorted(missing_config))}")
        if missing_files:
            details.append(f"missing host vars: {', '.join(sorted(missing_files))}")
        raise AutoconfSourceError(
            "home host sources disagree (" + "; ".join(details) + ")"
        )

    home_host_vars: dict[str, ConfigMapping] = {}
    for hostname, host_file in host_files.items():
        host_config = require_string_mapping(
            configured_hosts[hostname] or {},
            f"home-hosts.yml host {hostname}",
        )
        use_defaults = host_config.get("use_default_groups", True)
        extra_groups = _string_list(
            host_config.get("extra_groups", []),
            f"invalid home-hosts.yml settings for {hostname}",
        )
        if not isinstance(use_defaults, bool):
            raise AutoconfSourceError(f"invalid home-hosts.yml settings for {hostname}")
        groups = [*default_groups] if use_defaults else []
        groups.extend(extra_groups)
        unknown_groups = set(groups) - set(group_vars)
        if unknown_groups:
            names = ", ".join(sorted(unknown_groups))
            raise AutoconfSourceError(
                f"{hostname} references unknown home groups: {names}"
            )

        merged: ConfigMapping = {}
        for group_name in sorted(set(groups)):
            merged = deep_update(merged, group_vars[group_name])
        home_host_vars[hostname] = deep_update(merged, _load_config(host_file))
    return home_host_vars
