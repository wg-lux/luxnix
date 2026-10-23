"""Rebind an existing wheel venv to the configured Python without erasing metadata.

Called with the configured interpreter under the wheel installer's flock.
"""

import sys
import venv
from pathlib import Path


def repair(root: Path) -> None:
    settings = dict(
        line.split(" = ", 1)
        for line in (root / "pyvenv.cfg").read_text().splitlines()
        if " = " in line
    )
    current_abi = f"{sys.version_info.major}.{sys.version_info.minor}"
    if settings.get("version", "").split(".")[:2] != current_abi.split("."):
        raise RuntimeError("Python major/minor change requires an explicit runtime migration")
    # venv deliberately leaves existing symlinks alone, including dangling ones.
    # Keep site-packages intact so the downgrade guard still sees every version.
    for name in ("python", "python3", f"python{current_abi}"):
        (root / "bin" / name).unlink(missing_ok=True)
    venv.EnvBuilder(with_pip=True, symlinks=True).create(root)


if __name__ == "__main__":
    repair(Path(sys.argv[1]))
