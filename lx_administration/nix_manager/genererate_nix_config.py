# my_nix_manager/main.py
import os
from pathlib import Path
from .config_loader import load_config
from .template_renderer import render_nix_template
from .utils import (
    get_merged_host_config,
)
from .validation import validate_default_nix_file


def generate_nix_system_configuration(
    hostname: str,
    conf_parent: Path = Path("./conf"),
    system_type: str = "x86_64-linux",
    out_dir=Path("./tmp"),
) -> None:
    # conf_root = conf_parent / "nix-configs"

    # config_path = conf_root / f"{hostname}.yml"
    config_data = get_merged_host_config(hostname)

    print(f"Config data for {hostname}: {config_data}")

    template_name = config_data.get("template_name")

    template_root = conf_parent / "nix-templates"
    template_dir = template_root / "systems" / system_type / template_name

    # Render default.nix from template:
    default_nix = render_nix_template(template_dir, "default.nix.j2", config_data)
    default_nix_path = out_dir / "systems" / system_type / hostname / "default.nix"

    os.makedirs(default_nix_path.parent, exist_ok=True)

    with open(default_nix_path, "w") as f:
        f.write(default_nix)

    print(f"Generated {default_nix_path}")

    # validate_default_nix_file(default_nix_path)

    print(f"Validated {default_nix_path}")

    # render luxnix_nix from template:
    luxnix_nix = render_nix_template(template_dir, "luxnix.nix.j2", config_data)

    luxnix_nix_path = out_dir / "systems" / system_type / hostname / "luxnix.nix"

    with open(luxnix_nix_path, "w") as f:
        f.write(luxnix_nix)

    print(f"Generated {luxnix_nix_path}")
