# my_nix_manager/config_loader.py
import yaml
from typing import Any, Dict
from .nix_file_fixes import fix_yml_list_in_nix_file
from lx_administration.logging import get_logger, log_heading


def load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def write_nix_file(content, filepath, logger=None):
    if not logger:
        logger = get_logger("write_nix_file", reset=True)

    with open(filepath, "w") as f:
        f.write(content)

    fix_yml_list_in_nix_file(filepath, logger=logger)
