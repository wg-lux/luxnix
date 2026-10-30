#!/usr/bin/env python3
"""Validate the Git-scoped context graph without importing application code."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

import yaml


class UniqueLoader(yaml.SafeLoader):
    """Reject ambiguous duplicate keys, including keys introduced by YAML merges."""


def unique_mapping(loader, node):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)
REQUIRED = {
    "version",
    "tier",
    "path",
    "parent",
    "summary",
    "responsibilities",
    "boundaries",
    "entrypoints",
    "dependencies",
    "submodules",
    "contracts",
    "tests",
}
TIERS = {"root", "domain", "service", "package", "tool"}


def validate(root: Path) -> tuple[list[str], int]:
    root = root.resolve()
    errors: list[str] = []
    manifests: dict[Path, dict] = {}
    edges: dict[Path, list[Path]] = {}
    callers: dict[Path, list[Path]] = {}
    scope = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            "structure.yml",
            "**/structure.yml",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )

    def fail(manifest, message):
        errors.append(f"{manifest.relative_to(root)}: {message}")

    def text(value):
        return isinstance(value, str) and bool(value.strip())

    def reference(manifest, value, label, kind=None, base=None):
        if not text(value) or Path(value).is_absolute():
            fail(manifest, f"{label} must be a nonempty relative path")
            return None
        target = ((base or manifest.parent) / value).resolve()
        if not target.is_relative_to(root):
            fail(manifest, f"{label} escapes repository")
            return None
        if not target.exists():
            fail(manifest, f"{label} does not exist: {value}")
        elif kind == "file" and not target.is_file():
            fail(manifest, f"{label} must be a file: {value}")
        elif kind == "directory" and not target.is_dir():
            fail(manifest, f"{label} must be a directory: {value}")
        return target

    def rows(manifest, data, key, fields):
        value = data.get(key)
        if not isinstance(value, list):
            fail(manifest, f"{key} must be a list")
            return []
        valid = []
        names = set()
        for item in value:
            if not isinstance(item, dict) or any(not text(item.get(f)) for f in fields):
                fail(
                    manifest, f"{key} entries require text fields: {', '.join(fields)}"
                )
                continue
            if item["name"] in names:
                fail(manifest, f"duplicate {key} name: {item['name']}")
            names.add(item["name"])
            valid.append(item)
        return valid

    for name in sorted(set(filter(None, scope.stdout.split("\0")))):
        manifest = root / name
        if manifest.is_symlink():
            fail(manifest, "manifests must be regular files, not symlinks")
            continue
        try:
            data = yaml.load(manifest.read_text(encoding="utf-8"), Loader=UniqueLoader)
        except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
            fail(manifest, f"cannot load manifest: {exc}")
            continue
        if not isinstance(data, dict):
            fail(manifest, "manifest must be a mapping")
            continue
        manifests[manifest] = data
        edges[manifest] = []
        missing = REQUIRED - data.keys()
        if missing:
            fail(manifest, f"missing required keys: {', '.join(sorted(missing))}")
        if type(data.get("version")) is not int or data["version"] != 1:
            fail(manifest, "version must be integer 1")
        if not text(data.get("tier")) or data["tier"] not in TIERS:
            fail(manifest, "invalid tier")
        expected_path = manifest.parent.relative_to(root).as_posix()
        if data.get("path") != expected_path:
            fail(manifest, f"path must be {expected_path}")
        if not text(data.get("summary")):
            fail(manifest, "summary must be nonempty text")
        for key in ("responsibilities", "boundaries"):
            value = data.get(key)
            if not isinstance(value, list) or not value or not all(map(text, value)):
                fail(manifest, f"{key} must be a nonempty list of text")
        for item in rows(manifest, data, "entrypoints", ("name", "file", "purpose")):
            reference(manifest, item["file"], "entrypoints.file", "file")
        for item in rows(manifest, data, "contracts", ("name", "doc")):
            reference(manifest, item["doc"], "contracts.doc", "file")
        # Optional explicit file inventory; arbitrary custom metadata remains intact.
        files = data.get("files", [])
        if not isinstance(files, list):
            fail(manifest, "files must be a list of relative file paths")
        else:
            for value in files:
                reference(manifest, value, "files", "file")
        deps = data.get("dependencies")
        if not isinstance(deps, dict):
            fail(manifest, "dependencies must be a mapping")
        else:
            for key in ("internal", "external"):
                values = deps.get(key)
                if not isinstance(values, list) or not all(map(text, values)):
                    fail(manifest, f"dependencies.{key} must be a list of text")
                elif key == "internal":
                    for value in values:
                        reference(
                            manifest, value, "dependencies.internal", "directory", root
                        )
        tests = data.get("tests")
        if not isinstance(tests, dict) or not text(tests.get("command")):
            fail(manifest, "tests must contain directory and nonempty command")
        else:
            reference(manifest, tests.get("directory"), "tests.directory", "directory")
        for item in rows(
            manifest, data, "submodules", ("name", "path", "manifest", "summary")
        ):
            directory = reference(
                manifest, item["path"], "submodules.path", "directory"
            )
            child = reference(manifest, item["manifest"], "submodules.manifest", "file")
            if child is None or directory is None:
                continue
            if child != directory / "structure.yml":
                fail(manifest, "submodules.manifest must be path/structure.yml")
            if directory == manifest.parent or not directory.is_relative_to(
                manifest.parent
            ):
                fail(manifest, "submodule must be a strict descendant directory")
            if child in edges[manifest]:
                fail(manifest, f"duplicate child manifest: {item['manifest']}")
            edges[manifest].append(child)
            callers.setdefault(child, []).append(manifest)

    entry = root / "structure.yml"
    if entry not in manifests:
        errors.append("structure.yml: root manifest is missing or invalid")
    for manifest, data in manifests.items():
        parents = callers.get(manifest, [])
        if manifest == entry:
            if data.get("parent") is not None or data.get("tier") != "root" or parents:
                fail(manifest, "root must have tier root, null parent and no caller")
            continue
        if data.get("tier") == "root":
            fail(manifest, "only the repository manifest may use tier root")
        parent = reference(manifest, data.get("parent"), "parent", "file")
        if parent is not None:
            if parent not in manifests:
                fail(manifest, "parent is not a discovered valid manifest")
            if parent.parent == manifest.parent or not manifest.parent.is_relative_to(
                parent.parent
            ):
                fail(manifest, "parent must belong to an ancestor directory")
        if len(parents) != 1 or parents[0] != parent:
            fail(manifest, "parent must match exactly one caller's manifest")
    for children in edges.values():
        for child in children:
            if child not in manifests:
                errors.append(
                    f"{child.relative_to(root)}: "
                    "child is not a discovered valid manifest"
                )
    reached: set[Path] = set()
    pending = [entry]
    while pending:
        node = pending.pop()
        if node not in reached:
            reached.add(node)
            pending.extend(edges.get(node, []))
    for manifest in manifests.keys() - reached:
        fail(manifest, "manifest is unreachable from structure.yml")
    return errors, len(manifests)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    try:
        errors, count = validate(args.root)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Structure validation failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Structure validation passed: {count} manifests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
