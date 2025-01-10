from pathlib import Path
from lx_administration.nix_manager import generate_nix_system_configuration
from yaml import safe_load


def build_nix_system_configs(conf_parent: Path, out_dir: Path) -> None:
    assert conf_parent.is_dir()
    conf_dir = conf_parent / "nix-configs"

    print(f"Building NixOS system configurations from {conf_dir}")
    for template in conf_dir.glob("*.yml"):
        print(f"Generating NixOS system configuration for {template}")
        hostname = template.stem

        generate_nix_system_configuration(
            hostname,
            conf_parent=conf_parent,
            system_type="x86_64-linux",
            out_dir=out_dir,
        )


if __name__ == "__main__":
    build_nix_system_configs(Path("./conf"), Path("./"))
