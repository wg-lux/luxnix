from pydantic import BaseModel

# make model based on merged_vars/gc-06.yml
from typing import Dict, List, Union, Optional
import yaml
from lx_administration.logging import get_logger


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


class MergedHostVars(BaseModel):
    group_luxnix: Optional[Dict[str, Union[List[str], str]]] = {}
    group_roles: Optional[Dict[str, Union[List[str], str]]] = {}
    group_services: Optional[Dict[str, Union[List[str], str]]] = {}
    host_luxnix: Optional[Dict[str, Union[List[str], str]]] = {}
    host_roles: Optional[Dict[str, Union[List[str], str]]] = {}
    host_services: Optional[Dict[str, Union[List[str], str]]] = {}
    template_name: Optional[str] = "main"

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
        host_luxnix = data.get("host_luxnix", {})
        host_roles = data.get("host_roles", {})
        host_services = data.get("host_services", {})
        template_name = data.get("template_name", "main")

        mergerd_vars = cls(
            group_luxnix=group_luxnix,
            group_roles=group_roles,
            group_services=group_services,
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
        role_configs = deep_update(role_configs, self.host_roles)
        role_configs = _dictkey_replace_underscore_keys(role_configs)

        return role_configs

    def prepare_services(self):
        from lx_administration.autoconf.imports.utils import deep_update

        service_configs = {}

        # merge group_services and host_services
        service_configs = deep_update(service_configs, self.group_services)
        service_configs = deep_update(service_configs, self.host_services)

        service_configs = _dictkey_replace_underscore_keys(service_configs)

        return service_configs

    def prepare_luxnix(self):
        from lx_administration.autoconf.imports.utils import deep_update

        luxnix_configs = {}

        # merge group_luxnix and host_luxnix
        luxnix_configs = deep_update(luxnix_configs, self.group_luxnix)
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
        luxnix = self.prepare_luxnix()
        logger.info(f"luxnix: {luxnix}")
        platform = luxnix.get("generic-settings.hostPlatform").replace('"', "")
        return platform
