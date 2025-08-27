# my_nix_manager/main.py
import os
from pathlib import Path
from .template_renderer import render_nix_template
from .utils import write_nix_file
from lx_administration.logging import log_heading

from lx_administration.models import MergedHostVars

from .home import home_pipe


def get_template_dir_for_host(
    merged_vars: MergedHostVars, nix_template_dir: Path, logger=None
) -> Path:
    template_name: str = merged_vars.template_name or "main"
    host_platform: str = merged_vars.get_host_platform(logger=logger)
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
    # Do not create a new file logger; use shared pipeline logger if provided
    if logger:
        log_heading(logger, f"Generating default.nix for {hostname}")

    template_dir = get_template_dir_for_host(merged_vars, nix_template_dir, logger=logger)

    # Render default.nix from template:
    host_platform: str = merged_vars.get_host_platform(logger=logger)

    exported_host_config = merged_vars.export_host_config(logger=logger)

    default_nix = render_nix_template(
        str(template_dir), "default.nix.j2", exported_host_config
    )
    default_nix_path = out_dir / "systems" / host_platform / hostname / "default.nix"

    os.makedirs(default_nix_path.parent, exist_ok=True)

    write_nix_file(default_nix, default_nix_path, logger=logger)


def pipe(
    autoconf_out: Path,
    nix_template_dir=Path("./conf"),
    nix_out: Path = Path("."),
    logger=None,
    home_only_hosts: set[str] = set() #home system issue,added home_only_hosts
):
    # load config data
    # Do not create a new logger here; rely on the shared pipeline logger

    merged_vars_dir = autoconf_out / "merged_vars"

    for merged_vars_file in merged_vars_dir.glob("*.yml"):
        hostname = merged_vars_file.stem
        if hostname in home_only_hosts:#home system issue,
            if logger:
                logger.info(f"[SKIP SYSTEM CONFIG] {hostname} is home-only")#home system issue,to skips generating systems/x86_64-linux/<host>/default.nix.
            continue#home system issue,

        merged_vars = MergedHostVars.load_from_file(str(merged_vars_file), logger=logger)

        try:
            _host_platform = merged_vars.get_host_platform(logger=logger)
            export = True

        except Exception as e:
            if logger:
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

    home_pipe(
        autoconf_out / "home_merged_vars",
        nix_template_dir,
        nix_out,
        logger=logger,
    )

