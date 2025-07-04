from pydantic import BaseModel
from collections import defaultdict
import pprint
# make model based on merged_vars/gc-06.yml
from typing import Dict, List, Union, Optional, Any
import yaml
from lx_administration.logging import get_logger
from lx_administration.autoconf.imports.utils import deep_update, _dictkey_replace_underscore_keys
from lx_administration.autoconf.imports.utils import deep_update

# TODO REFACTOR
def _dictkey_replace_underscore_keys(
    config_data: Dict[str, Union[List[str], str]], logger=None
) -> Dict[str, Union[List[str], str]]:
    transformed_config_data = {}
    if not logger:
        logger = get_logger("_dictkey_replace_underscore_keys")

    nix_keys = config_data.keys()

    for nix_key in nix_keys:
        value = config_data[nix_key]
        transformed_key = nix_key.replace("_", "-")
        if not nix_key == transformed_key:
            logger.info(f"Transforming key {nix_key} to {transformed_key}")
            transformed_config_data[transformed_key] = value
        else:
            transformed_config_data[nix_key] = config_data[nix_key]

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
    group_luxnix: Optional[Dict[str, Union[List[str], str]]] = {}
    group_roles: Optional[Dict[str, Union[List[str], str]]] = {}
    group_services: Optional[Dict[str, Union[List[str], str]]] = {}
    role_luxnix: Optional[Dict[str, Union[List[str], str]]] = {}
    role_roles: Optional[Dict[str, Union[List[str], str]]] = {}
    role_services: Optional[Dict[str, Union[List[str], str]]] = {}
    host_luxnix: Optional[Dict[str, Union[List[str], str]]] = {}
    host_roles: Optional[Dict[str, Union[List[str], str]]] = {}
    host_services: Optional[Dict[str, Union[List[str], str]]] = {}
    template_name: Optional[str] = "main"
    system_users: Optional[List[str]] = ["admin"]

    #for autoconfig
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

        if not logger:
            logger = get_logger("MergedHostVars-load_from_file")

        # get all required keys, assume empty dict as default value if key not found
        group_luxnix = data.get("group_luxnix", {})
        group_roles = data.get("group_roles", {})
        group_services = data.get("group_services", {})
        role_luxnix = data.get("role_luxnix", {})
        role_roles = data.get("role_roles", {})
        role_services = data.get("role_services", {})
        host_luxnix = data.get("host_luxnix", {})
        host_roles = data.get("host_roles", {})
        host_services = data.get("host_services", {})
        template_name = data.get("template_name", "main")
        home_users = data.get("home_users", [])
        home_configs = data.get("home_configs", {})

        mergerd_vars = cls(
            group_luxnix=group_luxnix,
            group_roles=group_roles,
            group_services=group_services,
            role_luxnix=role_luxnix,
            role_roles=role_roles,
            role_services=role_services,
            host_luxnix=host_luxnix,
            host_roles=host_roles,
            host_services=host_services,
            template_name=template_name,
        )

        return mergerd_vars

    def _is_aglnet_host(self):
        is_aglnet_host = False
        for role_name in self.group_roles.keys():
            if "aglnet.host" in role_name:
                if self.group_roles[role_name] == "true":
                    is_aglnet_host = True
                    break
        return is_aglnet_host

    def prepare_roles(self):
        from lx_administration.autoconf.imports.utils import deep_update

        role_configs = {}
        # merge group_roles and host_roles
        role_configs = deep_update(role_configs, self.group_roles)
        role_configs = deep_update(role_configs, self.role_roles)
        role_configs = deep_update(role_configs, self.host_roles)
        role_configs = _dictkey_replace_underscore_keys(role_configs)

        return role_configs
    
    # for autoconfig home configuartion
    
    '''def prepare_home_config(self, username=None): #working one
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
                    base_config[key] = val

        # Final nested structure using dotkey parser
        final_config = {
            section: dotkey_to_nested_dict(strip_common_prefix(data))
            for section, data in base_config.items()
        }
        final_config["stateVersion"] = "23.11"
        return final_config
'''


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
                    base_config[key] = val

        # Final nested structure using dotkey parser
        final_config = {
            section: dotkey_to_nested_dict(strip_common_prefix(data))
            for section, data in base_config.items()
        }
        final_config["stateVersion"] = "23.11"
        return final_config

    def prepare_services(self):
        from lx_administration.autoconf.imports.utils import deep_update

        service_configs = {}

        # merge group_services and host_services
        service_configs = deep_update(service_configs, self.group_services)
        service_configs = deep_update(service_configs, self.role_services)
        service_configs = deep_update(service_configs, self.host_services)

        service_configs = _dictkey_replace_underscore_keys(service_configs)

        return service_configs

    def prepare_luxnix(self):

        luxnix_configs = {}

        # merge group_luxnix and host_luxnix
        luxnix_configs = deep_update(luxnix_configs, self.group_luxnix)
        luxnix_configs = deep_update(luxnix_configs, self.role_luxnix)
        luxnix_configs = deep_update(luxnix_configs, self.host_luxnix)

        luxnix_configs = _dictkey_replace_underscore_keys(luxnix_configs)

        return luxnix_configs

    def export_host_config(self, logger=None):
        if not logger:
            logger = get_logger("MergedHostVars-export_host_config")
        roles = self.prepare_roles()
        services = self.prepare_services()
        luxnix = self.prepare_luxnix()

        host_config = {
            "role_configs": roles,
            "service_configs": services,
            "luxnix_configs": luxnix,
        }

        logger.info(f"Exported host config: {host_config}")

        return host_config

    def get_host_platform(self, logger=None):
        if not logger:
            logger = get_logger("MergedHostVars-get_host_platform")

        logger.info(f"Getting host platform for {self}")

        # First try regular system luxnix (as before)
        luxnix = self.prepare_luxnix()
        platform = luxnix.get("generic-settings.hostPlatform")

        if platform:
            return platform.replace('"', "")

        # Then fallback to home luxnix
        from lx_administration.autoconf.imports.utils import deep_update

        home_luxnix = deep_update(self.group_home_luxnix or {}, self.host_home_luxnix or {})
        platform = home_luxnix.get("luxnix.generic-settings.hostPlatform")

        if platform:
            return platform.replace('"', "")

        raise ValueError("Missing 'generic-settings.hostPlatform' in host_luxnix/group_luxnix or home_luxnix")

    # for autocofig of home configuration
    @classmethod
    def load_home_from_file(cls, file: str, logger=None):
        #print("in load_home_from_file in the merged_host_vars.py")
        with open(file, "r") as f:
            data = yaml.safe_load(f)

        if not logger:
            logger = get_logger("MergedHostVars-load_home_from_file")

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
            system_users=data.get("system_users", []),  #HERE:to use the sub user settings
            home_configs=data.get("home_configs", {}),  
            group_home_editors=data.get("group_home_editors", {}),
            host_home_editors=data.get("host_home_editors", {}),
            group_home_networking=data.get("group_home_networking", {}),
            host_home_networking=data.get("host_home_networking", {}),

            
        )
