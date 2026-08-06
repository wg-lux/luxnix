from lx_administration.logging import get_logger, shutdown_logging

from .config import AutoconfConfig
from .imports import build_home_merged_variables, import_source_data
from .nix import render_configurations


def run_pipeline(config: AutoconfConfig) -> None:
    """Run all import and rendering stages for an already validated config."""
    logger = get_logger("autoconf_pipeline", log_dir=config.log_dir, reset=True)
    try:
        import_source_data(
            config.ansible_root,
            config.output,
            subnet=config.inventory_subnet,
            system_group=config.inventory_system_group,
            logger=logger,
        )
        build_home_merged_variables(config.ansible_root, config.output, logger)

        render_configurations(config, logger=logger)
    finally:
        # Ensure all logging handlers are closed to avoid leaking file descriptors
        shutdown_logging()


def run_from_config(config: AutoconfConfig) -> None:
    """Run the pipeline using only options from the central YAML config."""
    config.require_valid()
    run_pipeline(config)
