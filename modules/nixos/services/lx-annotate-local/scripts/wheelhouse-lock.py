"""Select target artifacts from the application's validated pyproject/uv.lock pair."""

import email
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from urllib.parse import urlsplit
from zipfile import ZipFile

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version


def active_requirements(values):
    result = set()
    for value in values:
        requirement = Requirement(value)
        if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
            result.add(
                (
                    canonicalize_name(requirement.name),
                    tuple(sorted(requirement.extras)),
                    str(requirement.specifier),
                    requirement.url,
                )
            )
    return result


def validate_application(project, wheel):
    with ZipFile(wheel) as archive:
        metadata_paths = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise ValueError("Application wheel must have exactly one METADATA file")
        metadata = email.message_from_bytes(archive.read(metadata_paths[0]))
    if (
        canonicalize_name(project["name"]) != "lx-annotate"
        or canonicalize_name(metadata["Name"]) != "lx-annotate"
        or Version(project["version"]) != Version(metadata["Version"])
    ):
        raise ValueError(
            "Application pyproject version/name does not match selected wheel"
        )
    if active_requirements(project["dependencies"]) != active_requirements(
        metadata.get_all("Requires-Dist", [])
    ):
        raise ValueError(
            "Application pyproject dependencies do not match selected wheel"
        )
    if SpecifierSet(project["requires-python"]) != SpecifierSet(
        metadata["Requires-Python"]
    ):
        raise ValueError("Application Python requirement does not match selected wheel")


def select_artifacts(lock, exported, tags=None):
    ranks = {tag: rank for rank, tag in enumerate(sys_tags() if tags is None else tags)}
    selected = {}
    for line in exported.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        pins = list(requirement.specifier)
        if (
            requirement.url
            or len(pins) != 1
            or pins[0].operator != "=="
            or "*" in pins[0].version
        ):
            raise ValueError(f"Expected exact registry requirement: {line}")
        name, version = canonicalize_name(requirement.name), pins[0].version
        packages = [
            package
            for package in lock["package"]
            if canonicalize_name(package["name"]) == name
            and package["version"] == version
        ]
        if len(packages) != 1 or "registry" not in packages[0]["source"]:
            raise ValueError(f"Expected one registry lock entry for {name}=={version}")
        package = packages[0]
        candidates = []
        for artifact in package.get("wheels", []):
            filename = Path(urlsplit(artifact["url"]).path).name
            wheel_name, wheel_version, _, wheel_tags = parse_wheel_filename(filename)
            compatible = wheel_tags & ranks.keys()
            if wheel_name != name or wheel_version != Version(version):
                raise ValueError(f"Wheel identity differs from lock entry: {filename}")
            if compatible:
                candidates.append(
                    (min(ranks[tag] for tag in compatible), filename, artifact)
                )
        source = not candidates
        artifact = (
            min(candidates, key=lambda candidate: candidate[:2])[2]
            if candidates
            else package.get("sdist")
        )
        if artifact is None:
            raise ValueError(
                f"No compatible wheel or source archive for {name}=={version}"
            )
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact["hash"]):
            raise ValueError(f"Missing SHA256 for {name}=={version}")
        if urlsplit(artifact["url"]).scheme != "https":
            raise ValueError(f"Expected HTTPS artifact for {name}=={version}")
        entry = dict(
            name=name,
            version=version,
            source=source,
            url=artifact["url"],
            filename=Path(urlsplit(artifact["url"]).path).name,
            sha256=artifact["hash"].removeprefix("sha256:"),
        )
        if name in selected and selected[name] != entry:
            raise ValueError(f"Conflicting active versions for {name}")
        selected[name] = entry
    return [selected[name] for name in sorted(selected)]


def main():
    source, wheel = map(Path, sys.argv[1:])
    project = tomllib.loads((source / "pyproject.toml").read_text())["project"]
    validate_application(project, wheel)
    exported = subprocess.check_output(
        [
            "uv",
            "export",
            "--project",
            str(source),
            "--locked",
            "--offline",
            "--no-default-groups",
            "--no-emit-project",
            "--no-header",
            "--no-annotate",
            "--no-hashes",
            "--no-python-downloads",
            "--python",
            sys.executable,
        ],
        text=True,
    )
    lock = tomllib.loads((source / "uv.lock").read_text())
    filename = re.sub(r"^[a-z0-9]{32}-", "", wheel.name)
    print(
        json.dumps(
            dict(
                version=project["version"],
                applicationFilename=filename,
                artifacts=select_artifacts(lock, exported),
            )
        )
    )


if __name__ == "__main__":
    main()
