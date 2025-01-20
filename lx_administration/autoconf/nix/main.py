# my_nix_manager/main.py
import os
from pathlib import Path
from .template_renderer import render_nix_template
from .utils import load_config, write_nix_file
from lx_administration.logging import get_logger, log_heading

from lx_administration.models import MergedHostVars


def get_template_dir_for_host(
    merged_vars: MergedHostVars, nix_template_dir: Path
) -> Path:
    template_name = merged_vars.template_name
    host_platform = merged_vars.get_host_platform()
    template_dir = nix_template_dir / "systems" / host_platform / template_name

    assert template_dir.is_dir(), f"Template directory {template_dir} not found"
    return template_dir


def generate_default_nix(
    hostname: str,
    merged_vars: MergedHostVars,
    nix_template_dir: Path = Path("./conf/nix-templates"),
    out_dir=Path("./tmp"),
    logger=None,
) -> None:
    # pretty print config data
    # pp = pprint.PrettyPrinter(indent=4)

    if not logger:
        logger = get_logger("generate_default_nix", reset=True)

    log_heading(logger, f"Generating default.nix for {hostname}")

    template_dir = get_template_dir_for_host(merged_vars, nix_template_dir)

    # Render default.nix from template:
    host_platform = merged_vars.get_host_platform()

    exported_host_config = merged_vars.export_host_config()

    import pprint

    pprint.pprint(exported_host_config)

    default_nix = render_nix_template(
        template_dir, "default.nix.j2", exported_host_config
    )
    default_nix_path = out_dir / "systems" / host_platform / hostname / "default.nix"

    os.makedirs(default_nix_path.parent, exist_ok=True)

    write_nix_file(default_nix, default_nix_path, logger=logger)


def pipe(
    autoconf_out: Path,
    nix_template_dir=Path("./conf"),
    nix_out: Path = Path("."),
    logger=None,
):
    # load config data
    if not logger:
        logger = get_logger("autoconf_nix_main_pipe", reset=True)

    merged_vars_dir = autoconf_out / "merged_vars"

    for merged_vars_file in merged_vars_dir.glob("*.yml"):
        hostname = merged_vars_file.stem
        merged_vars = MergedHostVars.load_from_file(merged_vars_file)

        if hostname == "s-01":
            import pprint

            pprint.pprint(merged_vars)

            try:
                _host_platform = merged_vars.get_host_platform()
                export = True

            except Exception as e:
                logger.warning(
                    f"Failed to get host platform for {hostname}: {e}; Skipping empty host"
                )
                export = False

            if export:
                generate_default_nix(
                    hostname,
                    merged_vars,
                    nix_template_dir=nix_template_dir,
                    out_dir=nix_out,
                    logger=logger,
                )
