# my_nix_manager/main.py
import os
from pathlib import Path
from .template_renderer import render_nix_template
from .utils import load_config, write_nix_file
from lx_administration.logging import get_logger, log_heading

import pprint


def host_config_get_host_vars(config_data: dict, verbose=False) -> dict:
    verbose = True

    host_vars = config_data.get("host_vars")
    if not host_vars:
        if verbose:
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(config_data)

        raise ValueError("No host_vars found in config_data")
    return host_vars


def host_config_get_template_name(config_data: dict) -> str:
    host_vars = host_config_get_host_vars(config_data)
    template_name = host_vars.get("template_name")
    assert template_name, "No template_name found in config_data"
    return template_name


def host_config_get_luxnix(config_data: dict) -> dict:
    luxnix = config_data.get("luxnix_configs", {})
    assert luxnix, "No luxnix found in host_vars"
    return luxnix


def host_config_get_platform(config_data: dict) -> str:
    luxnix = host_config_get_luxnix(config_data)
    assert luxnix, "No luxnix found"

    platform = luxnix.get("generic_settings.hostPlatform").replace('"', "")
    assert platform, "Key 'generic_settings.hostPlatform' not found in luxnix"

    return platform


def get_template_dir_for_host(config_data: dict, nix_template_dir: Path) -> Path:
    template_name = host_config_get_template_name(config_data)
    host_platform = host_config_get_platform(config_data)
    template_dir = nix_template_dir / "systems" / host_platform / template_name

    assert template_dir.is_dir(), f"Template directory {template_dir} not found"
    return template_dir


def generate_default_nix(
    hostname: str,
    config_data: dict,
    nix_template_dir: Path = Path("./conf/nix-templates"),
    out_dir=Path("./tmp"),
    logger=None,
) -> None:
    # pretty print config data
    # pp = pprint.PrettyPrinter(indent=4)

    config_data = config_data.copy()

    if not logger:
        logger = get_logger("generate_default_nix", reset=True)

    log_heading(logger, f"Generating default.nix for {hostname}")

    template_dir = get_template_dir_for_host(config_data, nix_template_dir)

    # Render default.nix from template:
    host_platform = host_config_get_platform(config_data)

    # Exchange underscores with dashes in keys
    transformed_config_data = config_data.copy()

    replace_underscore_keys = ["service_configs", "role_configs", "luxnix_configs"]

    for key in replace_underscore_keys:
        transformed_config_data[key] = {}
        if key in config_data:
            assert isinstance(config_data[key], dict), f"{key} is not a dict"
            nix_keys = config_data[key].keys()

            for nix_key in nix_keys:
                value = config_data[key][nix_key]
                transformed_key = nix_key.replace("_", "-")
                if not nix_key == transformed_key:
                    logger.info(f"Transforming key {nix_key} to {transformed_key}")
                transformed_config_data[key][transformed_key] = value

    default_nix = render_nix_template(
        template_dir, "default.nix.j2", transformed_config_data
    )
    default_nix_path = out_dir / "systems" / host_platform / hostname / "default.nix"

    os.makedirs(default_nix_path.parent, exist_ok=True)

    write_nix_file(default_nix, default_nix_path, logger=logger)


def pipe(autoconf_out: Path, nix_template_dir=Path("./conf"), logger=None):
    # load config data
    if not logger:
        logger = get_logger("autoconf_nix_main_pipe", reset=True)
    host_configs = load_config(autoconf_out / "host_configs.yml")

    for hostname, config_data in host_configs.items():
        logger.info(f"Generating default.nix for {hostname}")
        pp = pprint.PrettyPrinter(indent=4)
        logger.info(pp.pformat(config_data))

        generate_default_nix(
            hostname,
            config_data,
            nix_template_dir=nix_template_dir,
            out_dir=autoconf_out,
            logger=logger,
        )
