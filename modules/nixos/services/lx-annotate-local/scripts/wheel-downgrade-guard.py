"""Read-only version admission for the shared LX-Annotate wheel environment."""

from __future__ import annotations

import argparse
from email.parser import BytesParser
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

# The installer already requires pip in the selected virtualenv. Its vendored
# PEP 440 implementation is available before application dependencies exist.
from pip._vendor.packaging.utils import canonicalize_name
from pip._vendor.packaging.version import Version

PROTECTED_PACKAGES = frozenset({"lx-annotate", "endoreg-db", "lx-dtypes"})


def installed_versions() -> dict[str, Version]:
    result = {}
    for name in PROTECTED_PACKAGES:
        try:
            result[name] = Version(version(name))
        except PackageNotFoundError:
            continue
    return result


def reject_downgrade(
    name: str, candidate: Version, installed: dict[str, Version]
) -> None:
    current = installed.get(name)
    if current is not None and candidate < current:
        raise ValueError(
            f"Refusing shared-runtime downgrade: {name} {current} -> {candidate}. "
            "Use an independently provisioned, schema-compatible release environment."
        )


def validate_wheel(wheel: Path, expected: str, installed: dict[str, Version]) -> None:
    with ZipFile(wheel) as archive:
        entries = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(entries) != 1:
            raise ValueError(
                "Application wheel must contain exactly one package metadata record"
            )
        metadata = BytesParser().parsebytes(archive.read(entries[0]))
    if canonicalize_name(metadata.get("Name", "")) != "lx-annotate":
        raise ValueError("Configured application wheel does not contain lx-annotate")
    candidate = Version(metadata["Version"])
    if candidate != Version(expected):
        raise ValueError(
            "Application wheel version does not match configured packageVersion"
        )
    reject_downgrade("lx-annotate", candidate, installed)


def validate_report(
    report: object, installed: dict[str, Version]
) -> dict[str, Version]:
    if not isinstance(report, dict) or report.get("version") != "1":
        raise ValueError("Unsupported or missing pip installation report version")
    items = report.get("install")
    if not isinstance(items, list):
        raise ValueError("Missing pip installation plan")
    seen = set()
    selected = dict(installed)
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("metadata"), dict):
            raise ValueError("Malformed pip installation plan metadata")
        metadata = item["metadata"]
        if not isinstance(metadata.get("name"), str) or not metadata["name"]:
            raise ValueError("Missing pip candidate name")
        if not isinstance(metadata.get("version"), str):
            raise ValueError("Missing pip candidate version")
        name = canonicalize_name(metadata["name"])
        if name in seen:
            raise ValueError("Duplicate package in pip installation plan")
        seen.add(name)
        candidate = Version(metadata["version"])
        if name in PROTECTED_PACKAGES:
            reject_downgrade(name, candidate, installed)
            selected[name] = candidate
    return selected


def check_plan(
    requirements: list[str],
    pip_args: list[str],
    installed: dict[str, Version],
    *,
    no_deps: bool = False,
) -> dict[str, Version]:
    command = [sys.executable, "-m", "pip", "install", "--upgrade"]
    if no_deps:
        command.extend(["--no-deps", "--force-reinstall"])
    command.extend([*pip_args, *requirements, "--dry-run", "--report", "-", "--quiet"])
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode:
        # Resolver output can include authenticated index URLs. Retain only the
        # exit status here, and never reinterpret failure as an empty plan.
        raise ValueError(
            f"pip candidate resolution failed (exit {result.returncode}); "
            "no packages installed"
        )
    return validate_report(json.loads(result.stdout), installed)


def write_constraints(destination: Path, selected: dict[str, Version]) -> None:
    # Shipped beside this script from LuxNix's existing typed filesystem helper;
    # installing constraints must not depend on an installed application package.
    from wheel_guard_file_operations import atomic_write_file

    content = "".join(
        f"{name}=={value}\n" for name, value in sorted(selected.items())
    ).encode()
    atomic_write_file(destination=destination, content=[content], file_mode=0o600)
    print(
        json.dumps(
            {
                "event": "lx_annotate.wheel_constraints_published",
                "path": str(destination),
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--overrides-json", default="[]")
    parser.add_argument("--application-constraints", type=Path, required=True)
    parser.add_argument("--override-constraints", type=Path, required=True)
    parser.add_argument("pip_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    installed = installed_versions()
    validate_wheel(args.wheel, args.expected_version, installed)
    overrides = json.loads(args.overrides_json)
    if not isinstance(overrides, list) or not all(
        isinstance(value, str) for value in overrides
    ):
        raise ValueError("Dependency overrides must be a list of requirements")
    pip_args = args.pip_args[1:] if args.pip_args[:1] == ["--"] else args.pip_args
    application_plan = check_plan([str(args.wheel)], pip_args, installed)
    override_plan = dict(application_plan)
    if overrides:
        # Compare overrides against both the original environment and the
        # app-step plan; do not permit a transient upgrade followed by downgrade.
        override_plan = check_plan(overrides, pip_args, application_plan, no_deps=True)
    write_constraints(args.application_constraints, application_plan)
    write_constraints(args.override_constraints, override_plan)
    print(
        json.dumps(
            {
                "event": "lx_annotate.wheel_downgrade_guard_passed",
                "protected_packages": sorted(PROTECTED_PACKAGES),
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
