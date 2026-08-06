"""Write rendered Nix configuration files."""

import logging
from collections.abc import Iterable
from pathlib import Path

from .nix_file_fixes import fix_yml_list_in_nix_file

RenderedNixOutput = tuple[Path, str]


def write_nix_file(
    content: str,
    filepath: str | Path,
    logger: logging.Logger | None = None,
) -> None:
    """Write and normalize one rendered Nix file."""
    destination = Path(filepath)
    destination.write_text(content, encoding="utf-8")
    fix_yml_list_in_nix_file(destination, logger=logger)


def write_nix_outputs(
    outputs: Iterable[RenderedNixOutput],
    logger: logging.Logger | None = None,
) -> None:
    """Publish a sequence of fully rendered Nix outputs."""
    for destination, content in outputs:
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_nix_file(content, destination, logger=logger)
        if logger is not None:
            logger.info("Wrote generated Nix configuration: %s", destination)
