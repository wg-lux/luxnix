"""Repair wheel-venv Python or collected CA links without erasing metadata.

Called with the configured interpreter under the wheel installer's flock.
"""

import argparse
import os
import ssl
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


def repair_ca_bundle(root: Path, bundle: Path) -> None:
    """Recover collected certifi store links using the configured system trust."""
    if not (root / "pyvenv.cfg").is_file():
        raise RuntimeError("CA repair requires an existing virtual environment")
    bundle = bundle.resolve(strict=True)
    ssl.create_default_context(cafile=str(bundle))
    site = root / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    for relative in ("certifi/cacert.pem", "pip/_vendor/certifi/cacert.pem"):
        path = site / relative
        if not path.is_symlink() or path.exists():
            continue
        if not os.readlink(path).startswith("/nix/store/"):
            raise RuntimeError("Review the unexpected dangling CA bundle link")
        pending = path.with_name(".cacert.pem.pending")
        pending.symlink_to(bundle)
        pending.replace(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--ca-bundle", type=Path)
    args = parser.parse_args()
    if args.ca_bundle is not None:
        repair_ca_bundle(args.root, args.ca_bundle)
    else:
        repair(args.root)
