# my_nix_manager/config_loader.py
import yaml
from typing import Any, Dict


def load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)
