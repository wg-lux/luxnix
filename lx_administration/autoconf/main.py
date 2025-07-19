from pathlib import Path

from .imports.main import pipe as etl_pipe
from .nix.main import pipe as nix_pipe
from lx_administration.logging import get_logger, log_heading
from .imports.main import pipe as etl_pipe, home_etl

def pipe(
    ansible_root: Path,
    autoconf_out: Path,
    nix_out: Path,
    conf_parent: Path = Path("./conf"),
):
    logger = get_logger("autoconf_main_pipe", reset=True)
    _inventory ,home_only_hosts = etl_pipe(
        ansible_root, autoconf_out, subnet="172.16.255.0", logger=logger , 
    )
    """ for # home system issue,added home_only_hosts
     _inventory  = etl_pipe(
        ansible_root, autoconf_out, subnet="172.16.255.0", logger=logger , 
    )
    """
      # NEW: Home ETL
    home_etl(ansible_root, autoconf_out, logger)

    nix_pipe(
        autoconf_out=autoconf_out,
        nix_template_dir=conf_parent / "nix-templates",
        nix_out=nix_out,
        logger=logger,
        home_only_hosts=home_only_hosts, # home system issue,added home_only_hosts
    )
