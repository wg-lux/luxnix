"""Normalize comma-separated list syntax in generated Nix files."""

import logging
import re
from pathlib import Path

from lx_administration.logging import log_heading

LIST_ASSIGNMENT = re.compile(r"(\s*[A-Za-z0-9._-]+)\s*=\s*\[([^]]*)\];")


def fix_yml_list_in_nix_file(
    filepath: str | Path,
    logger: logging.Logger | None = None,
) -> None:
    source = Path(filepath)
    if logger is None:
        logger = logging.getLogger(__name__)

    log_heading(logger, f"Normalizing generated Nix lists in {source.name}")
    output = []
    for line_number, line in enumerate(
        source.read_text(encoding="utf-8").splitlines(keepends=True), start=1
    ):
        match = LIST_ASSIGNMENT.search(line)
        if match is None:
            output.append(line)
            continue

        left_side, list_content = match.groups()
        if "," not in list_content:
            output.append(line)
            continue

        items = [
            item.strip().strip("'\"")
            for item in list_content.split(",")
            if item.strip()
        ]
        new_list = "[" + " ".join(f'"{item}"' for item in items) + "]"
        line_ending = "\n" if line.endswith("\n") else ""
        output.append(f"{left_side} = {new_list};{line_ending}")
        logger.info("Normalized comma-separated list on line %d", line_number)

    source.write_text("".join(output), encoding="utf-8")
