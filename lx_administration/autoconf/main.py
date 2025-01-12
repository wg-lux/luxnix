from pathlib import Path

from .imports.main import pipe as etl_pipe
from .nix.main import pipe as nix_pipe
from lx_administration.logging import get_logger, log_heading


def pipe(ansible_root: Path, autoconf_out: Path, conf_parent: Path = Path("./conf")):
    logger = get_logger("autoconf_main_pipe", reset=True)
    etl_result = etl_pipe(
        ansible_root, autoconf_out, subnet="172.16.255.0", logger=logger
    )
    host_facts, inventory, host_configs, roles, group_vars, host_vars = etl_result

    nix_pipe(
        autoconf_out, nix_template_dir=conf_parent / "nix-templates", logger=logger
    )
