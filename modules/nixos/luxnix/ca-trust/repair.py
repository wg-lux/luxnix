"""Relink certifi bundles in mutable Python environments to the system CA bundle.

pip installs certifi with its own cacert.pem, and pip vendors another copy.
Neither follows the NixOS trust store, so a distrusted root stays trusted
until each file points at the regenerated system bundle again. Reinstalling
certifi restores the copied file, so callers run this after every install.
"""

import argparse
import os
import sys
from pathlib import Path

PATTERNS = (
    "lib/python*/site-packages/certifi/cacert.pem",
    "lib/python*/site-packages/*/_vendor/certifi/cacert.pem",
)


def certifi_bundles(root: Path) -> list[Path]:
    return sorted({path for pattern in PATTERNS for path in root.glob(pattern)})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True, help="system CA bundle")
    parser.add_argument("--check", action="store_true", help="report stale bundles without changing them")
    parser.add_argument("environments", type=Path, nargs="+", help="virtualenv roots")
    args = parser.parse_args()

    bundle = args.bundle.resolve(strict=True)
    stale = []
    for root in args.environments:
        if not (root / "pyvenv.cfg").is_file():
            print(f"ERROR: {root} is not a Python virtual environment", file=sys.stderr)
            return 1
        for pem in certifi_bundles(root):
            if pem.is_symlink() and pem.resolve() == bundle:
                continue
            if args.check:
                stale.append(pem)
                continue
            temporary = pem.with_name(".cacert.pem.luxnix-ca-trust")
            temporary.unlink(missing_ok=True)
            temporary.symlink_to(bundle)
            os.replace(temporary, pem)
            print(f"Relinked {pem} -> {bundle}")

    if stale:
        print("ERROR: certifi bundles do not use the system CA bundle:", file=sys.stderr)
        for pem in stale:
            print(f"  {pem}", file=sys.stderr)
        print("Run luxnix-ca-trust-repair on the environment to repair it.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
