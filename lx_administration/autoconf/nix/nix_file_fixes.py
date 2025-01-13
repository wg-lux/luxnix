import re
from pathlib import Path
from datetime import datetime as dt
from lx_administration.logging import get_logger, log_heading


def fix_yml_list_in_nix_file(
    filepath, log_dir: Path = Path("./autoconf/logs"), logger=None
):
    log_dir.mkdir(exist_ok=True)

    if not logger:
        logger = get_logger("fix_yml_list_in_nix_file", reset=True)

    with open(filepath, "r") as f:
        lines = f.readlines()

    timestamp = dt.now().strftime("%Y-%m-%d %H:%M:%S")
    log_heading(logger, f"Fixing lists in Nix file: {filepath} at {timestamp}")

    output = []
    pattern = re.compile(r"(\s*[A-Za-z0-9._-]+)\s*=\s*\[([^]]*)\];")
    for i, line in enumerate(lines):
        original_line = line
        match = pattern.search(line)
        if match:
            left_side, list_content = match.groups()
            items = [
                i.strip().strip("'\"") for i in list_content.split(",") if i.strip()
            ]
            # Convert items to Nix-style list
            new_list = "[" + " ".join(f'"{item}"' for item in items) + "]"
            line = f"{left_side} = {new_list};"

            logger.info(
                f"\nFound list in line {i}: {original_line.strip()}\nFixed line {i}: {line.strip()}\n"
            )

        output.append(line)

    with open(f"{filepath}", "w") as f:
        f.writelines(output)
