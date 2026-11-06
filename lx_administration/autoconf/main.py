import logging
import tempfile
from dataclasses import replace
from pathlib import Path

from lx_administration.logging import get_logger, shutdown_logging
from lx_administration.permissions import ensure_private_directory
from .publication import publication_lock, publish_files

from .config import AutoconfConfig
from .imports import build_home_merged_variables, import_source_data
from .nix import render_configurations
from .nix.main import render_isolated_configurations


def run_pipeline(config: AutoconfConfig) -> None:
    """Run all import and rendering stages for an already validated config."""
    logger = get_logger("autoconf_pipeline", log_dir=config.log_dir, reset=True)
    try:
        # Imports and formatting must all succeed before any canonical artifact
        # changes. The durable journal spans intermediates and both Nix trees.
        root = config.output
        with publication_lock(root):
            with tempfile.TemporaryDirectory(
                prefix=".autoconf-pipeline-", dir=root
            ) as temporary:
                stage = Path(temporary)
                staged = replace(
                    config, output=stage / "intermediates", nix_output=stage / "nix"
                )
                import_source_data(
                    staged.ansible_root,
                    staged.output,
                    subnet=staged.inventory_subnet,
                    system_group=staged.inventory_system_group,
                    logger=logger,
                )
                build_home_merged_variables(staged.ansible_root, staged.output, logger)
                render_configurations(staged, logger=logger)
                outputs = []
                for source in staged.output.rglob("*.yml"):
                    destination = config.output / source.relative_to(staged.output)
                    ensure_private_directory(destination.parent)
                    outputs.append((destination, source.read_bytes(), 0o600))
                for directory in ("merged_vars", "home_merged_vars"):
                    names = {p.name for p in (staged.output / directory).glob("*.yml")}
                    outputs.extend(
                        (p, None, 0o600)
                        for p in (config.output / directory).glob("*.yml")
                        if p.name not in names
                    )
                outputs.extend(
                    (
                        config.nix_output / source.relative_to(staged.nix_output),
                        source.read_bytes(),
                        0o644,
                    )
                    for source in staged.nix_output.rglob("*.nix")
                )
                publish_files(
                    outputs,
                    root=root,
                    locked=True,
                    allowed_roots=(config.output, config.nix_output),
                )
    finally:
        # Ensure all logging handlers are closed to avoid leaking file descriptors
        shutdown_logging()


def run_from_config(config: AutoconfConfig) -> None:
    """Run the pipeline using only options from the central YAML config."""
    config.require_valid()
    run_pipeline(config)


def run_isolated_nix_render(config: AutoconfConfig, nix_output: Path) -> None:
    """Render existing merged data without importing or replacing configured output."""
    logger = logging.Logger("autoconf_isolated_nix_render")
    logger.addHandler(logging.NullHandler())
    render_isolated_configurations(config, nix_output=nix_output, logger=logger)
