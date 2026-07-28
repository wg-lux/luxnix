from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import yaml
from lx_administration.autoconf.imports.utils import deep_update


# Local helper that accepts an optional logger and does not create its own
# Replaces underscores with dashes in top-level keys
def _replace_unquoted_underscores(value: str) -> str:
    result: List[str] = []
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
    config_data: Dict[str, Any], logger=None
) -> Dict[str, Any]:
    transformed_config_data: Dict[str, Any] = {}
    for nix_key, value in config_data.items():
        transformed_key = _replace_unquoted_underscores(nix_key)
        if nix_key != transformed_key:
            if logger:
                logger.info(f"Transforming key {nix_key} to {transformed_key}")
            transformed_config_data[transformed_key] = value
        else:
            transformed_config_data[nix_key] = value
    return transformed_config_data


def dotkey_to_nested_dict(flat_dict):
    nested = {}
    for flat_key, value in flat_dict.items():
        keys = flat_key.split(".")
        d = nested
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value
    return nested


def strip_common_prefix(flat_dict):
    """Auto-detect and strip common prefix like 'cli.', 'luxnix.', etc."""
    if not flat_dict:
        return flat_dict

    first_key = next(iter(flat_dict))
    if "." not in first_key:
        return flat_dict  # Already fine

    prefix = first_key.split(".")[0] + "."

    if all(k.startswith(prefix) for k in flat_dict):
        return {k[len(prefix):]: v for k, v in flat_dict.items()}
    else:
        return flat_dict


class MergedHostVars(BaseModel):
    group_luxnix: Optional[Dict[str, Any]] = {}
    group_roles: Optional[Dict[str, Any]] = {}
    group_services: Optional[Dict[str, Any]] = {}
    group_nixos: Optional[Dict[str, Any]] = {}
    group_imports: Optional[List[str]] = []
    role_luxnix: Optional[Dict[str, Any]] = {}
    role_roles: Optional[Dict[str, Any]] = {}
    role_services: Optional[Dict[str, Any]] = {}
    role_nixos: Optional[Dict[str, Any]] = {}
    role_imports: Optional[List[str]] = []
    host_luxnix: Optional[Dict[str, Any]] = {}
    host_roles: Optional[Dict[str, Any]] = {}
    host_services: Optional[Dict[str, Any]] = {}
    host_nixos: Optional[Dict[str, Any]] = {}
    host_imports: Optional[List[str]] = []
    template_name: Optional[str] = "main"
    system_users: Optional[List[str]] = ["admin"]

    # for autoconfig
    home_users: Optional[List[str]] = []
    home_configs: Optional[Dict[str, Dict[str, str]]] = {}

    group_home_roles: Optional[Dict[str, Any]] = {}
    host_home_roles: Optional[Dict[str, Any]] = {}

    group_home_services: Optional[Dict[str, Any]] = {}
    host_home_services: Optional[Dict[str, Any]] = {}

    group_home_luxnix: Optional[Dict[str, Any]] = {}
    host_home_luxnix: Optional[Dict[str, Any]] = {}

    group_home_cli: Optional[Dict[str, Any]] = {}
    host_home_cli: Optional[Dict[str, Any]] = {}

    group_home_desktops: Optional[Dict[str, Any]] = {}
    host_home_desktops: Optional[Dict[str, Any]] = {}

    group_home_editors: Optional[Dict[str, Any]] = {}
    host_home_editors: Optional[Dict[str, Any]] = {}

    group_home_networking: Optional[Dict[str, Any]] = {}
    host_home_networking: Optional[Dict[str, Any]] = {}

    @classmethod
    def load_from_file(cls, file: str, logger=None):
        with open(file, "r") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            data = {}

        # get all required keys, assume empty dict as default value if key not found
        group_luxnix = data.get("group_luxnix", {})
        group_roles = data.get("group_roles", {})
        group_services = data.get("group_services", {})
        group_nixos = data.get("group_nixos", {})
        group_imports = data.get("group_imports", [])
        role_luxnix = data.get("role_luxnix", {})
        role_roles = data.get("role_roles", {})
        role_services = data.get("role_services", {})
        role_nixos = data.get("role_nixos", {})
        role_imports = data.get("role_imports", [])
        host_luxnix = data.get("host_luxnix", {})
        host_roles = data.get("host_roles", {})
        host_services = data.get("host_services", {})
        host_nixos = data.get("host_nixos", {})
        host_imports = data.get("host_imports", [])
        template_name = data.get("template_name", "main")

        mergerd_vars = cls(
            group_luxnix=group_luxnix,
            group_roles=group_roles,
            group_services=group_services,
            group_nixos=group_nixos,
            group_imports=group_imports,
            role_luxnix=role_luxnix,
            role_roles=role_roles,
            role_services=role_services,
            role_nixos=role_nixos,
            role_imports=role_imports,
            host_luxnix=host_luxnix,
            host_roles=host_roles,
            host_services=host_services,
            host_nixos=host_nixos,
            host_imports=host_imports,
            template_name=template_name,
        )

        return mergerd_vars

    def prepare_roles(self, logger=None):
        role_configs: Dict[str, Any] = {}
        # merge group_roles and host_roles
        role_configs = deep_update(role_configs, self.group_roles)
        role_configs = deep_update(role_configs, self.role_roles)
        role_configs = deep_update(role_configs, self.host_roles)
        role_configs = _dictkey_replace_underscore_keys(role_configs, logger=logger)
        return role_configs

    # for autoconfig home configuration
    def prepare_home_config(self, username=None):
        base_config = {
            "cli": deep_update(self.group_home_cli or {}, self.host_home_cli or {}),
            "desktops": deep_update(self.group_home_desktops or {}, self.host_home_desktops or {}),
            "editors": deep_update(self.group_home_editors or {}, self.host_home_editors or {}),
            "networking": deep_update(self.group_home_networking or {}, self.host_home_networking or {}),
            "services": deep_update(self.group_home_services or {}, self.host_home_services or {}),
            "luxnix": deep_update(self.group_home_luxnix or {}, self.host_home_luxnix or {}),
            "roles": deep_update(self.group_home_roles or {}, self.host_home_roles or {}),
        }

        # Apply user-specific overrides
        if username and self.home_configs and username in self.home_configs:
            overrides = self.home_configs.get(username, {})
            for key, val in overrides.items():
                if "." in key:
                    section = key.split(".")[0]
                    if section not in base_config:
                        base_config[section] = {}
                    base_config[section] = deep_update(base_config[section], {key: val})
                else:
                    # fallback: treat top-level (e.g. plain "networking")
                    base_config[key] = val  # type: ignore[assignment]

        # Final nested structure using dotkey parser
        final_config = {
            section: dotkey_to_nested_dict(strip_common_prefix(data))
            for section, data in base_config.items()
        }
        final_config["stateVersion"] = "23.11"  # type: ignore[index]
        return final_config

    def prepare_services(self, logger=None):
        service_configs: Dict[str, Any] = {}
        # merge group_services and host_services
        service_configs = deep_update(service_configs, self.group_services)
        service_configs = deep_update(service_configs, self.role_services)
        service_configs = deep_update(service_configs, self.host_services)
        service_configs = _dictkey_replace_underscore_keys(service_configs, logger=logger)
        return service_configs

    def prepare_luxnix(self, logger=None):
        luxnix_configs: Dict[str, Any] = {}
        # merge group_luxnix and host_luxnix
        luxnix_configs = deep_update(luxnix_configs, self.group_luxnix)
        luxnix_configs = deep_update(luxnix_configs, self.role_luxnix)
        luxnix_configs = deep_update(luxnix_configs, self.host_luxnix)
        luxnix_configs = _dictkey_replace_underscore_keys(luxnix_configs, logger=logger)
        return luxnix_configs

    def prepare_nixos(self, logger=None):
        nixos_configs: Dict[str, Any] = {}
        nixos_configs = deep_update(nixos_configs, self.group_nixos)
        nixos_configs = deep_update(nixos_configs, self.role_nixos)
        nixos_configs = deep_update(nixos_configs, self.host_nixos)
        nixos_configs = _dictkey_replace_underscore_keys(nixos_configs, logger=logger)
        return nixos_configs

    def prepare_imports(self):
        imports: List[str] = []
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

    def export_host_config(self, logger=None):
        roles = self.prepare_roles(logger=logger)
        services = self.prepare_services(logger=logger)
        luxnix = self.prepare_luxnix(logger=logger)
        nixos = self.prepare_nixos(logger=logger)
        imports = self.prepare_imports()

        host_config = {
            "role_configs": roles,
            "service_configs": services,
            "luxnix_configs": luxnix,
            "nixos_configs": nixos,
            "import_configs": imports,
        }

        if logger:
            logger.info(f"Exported host config: {host_config}")

        return host_config

    def get_host_platform(self, logger=None):
        if logger:
            logger.info(f"Getting host platform for {self}")

        # First try regular system luxnix (as before)
        luxnix = self.prepare_luxnix(logger=logger)
        platform = luxnix.get("generic-settings.hostPlatform")

        if isinstance(platform, str):
            return platform.replace('"', "")

        # Then fallback to home luxnix
        home_luxnix = deep_update(self.group_home_luxnix or {}, self.host_home_luxnix or {})
        platform = home_luxnix.get("luxnix.generic-settings.hostPlatform")

        if isinstance(platform, str):
            return platform.replace('"', "")

        raise ValueError("Missing 'generic-settings.hostPlatform' in host_luxnix/group_luxnix or home_luxnix")

    @classmethod
    def load_home_from_file(cls, file: str, logger=None):
        with open(file, "r") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            data = {}

        return cls(
            host_home_roles=data.get("host_home_roles", {}),
            group_home_roles=data.get("group_home_roles", {}),
            host_home_services=data.get("host_home_services", {}),
            group_home_services=data.get("group_home_services", {}),
            host_home_luxnix=data.get("host_home_luxnix", {}),
            group_home_luxnix=data.get("group_home_luxnix", {}),
            host_home_cli=data.get("host_home_cli", {}),
            group_home_cli=data.get("group_home_cli", {}),
            host_home_desktops=data.get("host_home_desktops", {}),
            group_home_desktops=data.get("group_home_desktops", {}),
            host_luxnix=data.get("host_luxnix", {}),
            host_nixos=data.get("host_nixos", {}),
            host_imports=data.get("host_imports", []),
            system_users=data.get("system_users", []),  # use sub user settings
            home_configs=data.get("home_configs", {}),
            group_home_editors=data.get("group_home_editors", {}),
            host_home_editors=data.get("host_home_editors", {}),
            group_home_networking=data.get("group_home_networking", {}),
            host_home_networking=data.get("host_home_networking", {}),
        )
