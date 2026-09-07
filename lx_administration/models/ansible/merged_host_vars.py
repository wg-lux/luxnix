from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from lx_administration.autoconf.imports.merge import deep_update
from lx_administration.yaml import load_unique_yaml_file

SYSTEM_FIELDS = frozenset(
    {
        "group_luxnix",
        "group_roles",
        "group_services",
        "group_nixos",
        "group_imports",
        "role_luxnix",
        "role_roles",
        "role_services",
        "role_nixos",
        "role_imports",
        "host_luxnix",
        "host_roles",
        "host_services",
        "host_nixos",
        "host_imports",
        "template_name",
    }
)

HOME_FIELDS = frozenset(
    {
        "host_home_roles",
        "group_home_roles",
        "host_home_services",
        "group_home_services",
        "host_home_luxnix",
        "group_home_luxnix",
        "host_home_cli",
        "group_home_cli",
        "host_home_desktops",
        "group_home_desktops",
        "host_luxnix",
        "host_nixos",
        "host_imports",
        "system_users",
        "home_configs",
        "group_home_editors",
        "host_home_editors",
        "group_home_networking",
        "host_home_networking",
    }
)


def _load_yaml_fields(source: str | Path, allowed: frozenset[str]) -> dict[str, Any]:
    path = Path(source)
    data = load_unique_yaml_file(path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return {name: data[name] for name in allowed if name in data}


def _merge_layers(*layers: dict[str, Any] | None) -> dict[str, Any]:
    """Merge configuration in declared group, role, then host order."""
    merged: dict[str, Any] = {}
    for layer in layers:
        merged = deep_update(merged, layer or {})
    return merged


def _replace_unquoted_underscores(value: str) -> str:
    result: list[str] = []
    in_double_quotes = False
    in_single_quotes = False
    escaped = False

    for char in value:
        if escaped:
            result.append(char)
            escaped = False
            continue

        if char == "\\":
            result.append(char)
            escaped = True
            continue

        if char == '"' and not in_single_quotes:
            in_double_quotes = not in_double_quotes
            result.append(char)
            continue

        if char == "'" and not in_double_quotes:
            in_single_quotes = not in_single_quotes
            result.append(char)
            continue

        if char == "_" and not in_double_quotes and not in_single_quotes:
            result.append("-")
            continue

        result.append(char)

    return "".join(result)


def _dictkey_replace_underscore_keys(
    config_data: dict[str, Any], logger=None
) -> dict[str, Any]:
    transformed_config_data: dict[str, Any] = {}
    for nix_key, value in config_data.items():
        transformed_key = _replace_unquoted_underscores(nix_key)
        if nix_key != transformed_key:
            if logger:
                logger.info(f"Transforming key {nix_key} to {transformed_key}")
            transformed_config_data[transformed_key] = value
        else:
            transformed_config_data[nix_key] = value
    return transformed_config_data


def dotkey_to_nested_dict(flat_dict: dict[str, Any]) -> dict[str, Any]:
    nested: dict[str, Any] = {}
    for flat_key, value in flat_dict.items():
        keys = flat_key.split(".")
        d = nested
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value
    return nested


def strip_common_prefix(flat_dict: dict[str, Any]) -> dict[str, Any]:
    """Auto-detect and strip common prefix like 'cli.', 'luxnix.', etc."""
    if not flat_dict:
        return flat_dict

    first_key = next(iter(flat_dict))
    if "." not in first_key:
        return flat_dict  # Already fine

    prefix = first_key.split(".")[0] + "."

    if all(key.startswith(prefix) for key in flat_dict):
        return {key[len(prefix) :]: value for key, value in flat_dict.items()}
    return flat_dict


class MergedHostVars(BaseModel):
    group_luxnix: dict[str, Any] | None = Field(default_factory=dict)
    group_roles: dict[str, Any] | None = Field(default_factory=dict)
    group_services: dict[str, Any] | None = Field(default_factory=dict)
    group_nixos: dict[str, Any] | None = Field(default_factory=dict)
    group_imports: list[str] | None = Field(default_factory=list)
    role_luxnix: dict[str, Any] | None = Field(default_factory=dict)
    role_roles: dict[str, Any] | None = Field(default_factory=dict)
    role_services: dict[str, Any] | None = Field(default_factory=dict)
    role_nixos: dict[str, Any] | None = Field(default_factory=dict)
    role_imports: list[str] | None = Field(default_factory=list)
    host_luxnix: dict[str, Any] | None = Field(default_factory=dict)
    host_roles: dict[str, Any] | None = Field(default_factory=dict)
    host_services: dict[str, Any] | None = Field(default_factory=dict)
    host_nixos: dict[str, Any] | None = Field(default_factory=dict)
    host_imports: list[str] | None = Field(default_factory=list)
    template_name: str | None = "main"
    system_users: list[str] | None = Field(default_factory=lambda: ["admin"])

    home_users: list[str] | None = Field(default_factory=list)
    home_configs: dict[str, dict[str, Any]] | None = Field(default_factory=dict)
    group_home_roles: dict[str, Any] | None = Field(default_factory=dict)
    host_home_roles: dict[str, Any] | None = Field(default_factory=dict)
    group_home_services: dict[str, Any] | None = Field(default_factory=dict)
    host_home_services: dict[str, Any] | None = Field(default_factory=dict)
    group_home_luxnix: dict[str, Any] | None = Field(default_factory=dict)
    host_home_luxnix: dict[str, Any] | None = Field(default_factory=dict)
    group_home_cli: dict[str, Any] | None = Field(default_factory=dict)
    host_home_cli: dict[str, Any] | None = Field(default_factory=dict)
    group_home_desktops: dict[str, Any] | None = Field(default_factory=dict)
    host_home_desktops: dict[str, Any] | None = Field(default_factory=dict)
    group_home_editors: dict[str, Any] | None = Field(default_factory=dict)
    host_home_editors: dict[str, Any] | None = Field(default_factory=dict)
    group_home_networking: dict[str, Any] | None = Field(default_factory=dict)
    host_home_networking: dict[str, Any] | None = Field(default_factory=dict)

    @classmethod
    def load_from_file(cls, file: str | Path, logger=None) -> "MergedHostVars":
        return cls(**_load_yaml_fields(file, SYSTEM_FIELDS))

    def prepare_roles(self, logger=None) -> dict[str, Any]:
        role_configs = _merge_layers(
            self.group_roles,
            self.role_roles,
            self.host_roles,
        )
        role_configs = _dictkey_replace_underscore_keys(role_configs, logger=logger)
        return role_configs

    def prepare_home_config(
        self,
        username: str | None,
        state_version: str,
    ) -> dict[str, Any]:
        base_config = {
            "cli": deep_update(self.group_home_cli or {}, self.host_home_cli or {}),
            "desktops": deep_update(
                self.group_home_desktops or {}, self.host_home_desktops or {}
            ),
            "editors": deep_update(
                self.group_home_editors or {}, self.host_home_editors or {}
            ),
            "networking": deep_update(
                self.group_home_networking or {}, self.host_home_networking or {}
            ),
            "services": deep_update(
                self.group_home_services or {}, self.host_home_services or {}
            ),
            "luxnix": deep_update(
                self.group_home_luxnix or {}, self.host_home_luxnix or {}
            ),
            "roles": deep_update(
                self.group_home_roles or {}, self.host_home_roles or {}
            ),
        }

        if username and self.home_configs and username in self.home_configs:
            overrides = self.home_configs.get(username, {})
            for key, value in overrides.items():
                if "." in key:
                    section = key.split(".")[0]
                    if section not in base_config:
                        base_config[section] = {}
                    base_config[section] = deep_update(
                        base_config[section], {key: value}
                    )
                else:
                    base_config[key] = value

        final_config: dict[str, Any] = {
            section: dotkey_to_nested_dict(strip_common_prefix(data))
            for section, data in base_config.items()
        }
        final_config["stateVersion"] = state_version
        return final_config

    def prepare_services(self, logger=None) -> dict[str, Any]:
        service_configs = _merge_layers(
            self.group_services,
            self.role_services,
            self.host_services,
        )
        service_configs = _dictkey_replace_underscore_keys(
            service_configs, logger=logger
        )
        return service_configs

    def prepare_luxnix(self, logger=None) -> dict[str, Any]:
        luxnix_configs = _merge_layers(
            self.group_luxnix,
            self.role_luxnix,
            self.host_luxnix,
        )
        luxnix_configs = _dictkey_replace_underscore_keys(luxnix_configs, logger=logger)
        return luxnix_configs

    def prepare_nixos(self, logger=None) -> dict[str, Any]:
        nixos_configs = _merge_layers(
            self.group_nixos,
            self.role_nixos,
            self.host_nixos,
        )
        nixos_configs = _dictkey_replace_underscore_keys(nixos_configs, logger=logger)
        return nixos_configs

    def prepare_imports(self) -> list[str]:
        imports: list[str] = []
        seen: set[str] = set()

        for import_expr in (
            (self.group_imports or [])
            + (self.role_imports or [])
            + (self.host_imports or [])
        ):
            if import_expr in seen:
                continue
            seen.add(import_expr)
            imports.append(import_expr)

        return imports

    def export_host_config(self, logger=None) -> dict[str, Any]:
        return {
            "role_configs": self.prepare_roles(logger=logger),
            "service_configs": self.prepare_services(logger=logger),
            "luxnix_configs": self.prepare_luxnix(logger=logger),
            "nixos_configs": self.prepare_nixos(logger=logger),
            "import_configs": self.prepare_imports(),
        }

    def get_host_platform(self, logger=None) -> str:
        luxnix = self.prepare_luxnix(logger=logger)
        platform = luxnix.get("generic-settings.hostPlatform")

        if isinstance(platform, str):
            return platform.replace('"', "")

        home_luxnix = _merge_layers(
            self.group_home_luxnix or {}, self.host_home_luxnix or {}
        )
        platform = home_luxnix.get("luxnix.generic-settings.hostPlatform")

        if isinstance(platform, str):
            return platform.replace('"', "")

        raise ValueError(
            "Missing 'generic-settings.hostPlatform' in host_luxnix/group_luxnix "
            "or home_luxnix"
        )

    @classmethod
    def load_home_from_file(cls, file: str | Path, logger=None) -> "MergedHostVars":
        values = _load_yaml_fields(file, HOME_FIELDS)
        values.setdefault("system_users", [])
        return cls(**values)
