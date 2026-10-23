"""Exercise drift rejection with isolated Git repositories and the actual graph."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import runpy
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
VALIDATE = runpy.run_path(str(ROOT / "scripts/lint_structure.py"))["validate"]


def manifest(path=".", parent=None):
    return {
        "version": 1,
        "tier": "root" if path == "." else "domain",
        "path": path,
        "parent": parent,
        "summary": "Example ownership boundary.",
        "responsibilities": ["Own configuration"],
        "boundaries": ["No runtime changes"],
        "entrypoints": [],
        "dependencies": {"internal": [], "external": []},
        "submodules": [],
        "contracts": [],
        "tests": {"directory": ".", "command": "pytest -q"},
    }


def write(root, name, data):
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    write(tmp_path, "structure.yml", manifest())
    return tmp_path


def link_child(repo):
    data = manifest()
    data["submodules"] = [
        {
            "name": "app",
            "path": "app",
            "manifest": "app/structure.yml",
            "summary": "App",
        }
    ]
    write(repo, "structure.yml", data)
    write(repo, "app/structure.yml", manifest("app", "../structure.yml"))
    return data


def test_repository_graph_is_valid():
    errors, count = VALIDATE(ROOT)
    assert errors == [], "\n".join(errors)
    assert count > 1


def test_valid_graph_preserves_custom_metadata_and_checks_all_paths(repo):
    data = link_child(repo)
    (repo / "entry.py").touch()
    data.update(
        entrypoints=[{"name": "entry", "file": "entry.py", "purpose": "Run"}],
        contracts=[{"name": "spec", "doc": "entry.py"}],
        files=["entry.py"],
        dependencies={"internal": ["app"], "external": ["Python"]},
        custom={"owner": "team", "protocol": "mTLS"},
    )
    write(repo, "structure.yml", data)
    before = (repo / "structure.yml").read_bytes()
    assert VALIDATE(repo) == ([], 2)
    assert (repo / "structure.yml").read_bytes() == before


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("version", True, "integer 1"),
        ("version", 2, "integer 1"),
        ("tier", [], "invalid tier"),
        ("summary", "", "summary"),
        ("responsibilities", [], "responsibilities"),
        ("boundaries", "text", "boundaries"),
        ("path", "elsewhere", "path must be"),
        ("parent", "structure.yml", "null parent"),
        ("entrypoints", {}, "must be a list"),
        ("entrypoints", [{}], "require text fields"),
        ("contracts", [{}], "require text fields"),
        ("submodules", [{}], "require text fields"),
        ("dependencies", [], "must be a mapping"),
        ("dependencies", {"internal": "app", "external": []}, "internal must be"),
        ("tests", {"directory": ".", "command": ""}, "nonempty command"),
        ("tests", {"command": "pytest"}, "relative path"),
        ("files", "entry.py", "files must be"),
    ],
)
def test_invalid_schema(repo, key, value, expected):
    data = manifest()
    data[key] = value
    write(repo, "structure.yml", data)
    assert expected in "\n".join(VALIDATE(repo)[0])


@pytest.mark.parametrize("key", list(manifest()))
def test_missing_required_fields(repo, key):
    data = manifest()
    del data[key]
    write(repo, "structure.yml", data)
    assert f"missing required keys: {key}" in "\n".join(VALIDATE(repo)[0])


@pytest.mark.parametrize(
    "update",
    [
        {"entrypoints": [{"name": "entry", "file": "missing", "purpose": "Run"}]},
        {"contracts": [{"name": "spec", "doc": "missing"}]},
        {"files": ["missing"]},
        {"dependencies": {"internal": ["missing"], "external": []}},
        {"tests": {"directory": "missing", "command": "pytest"}},
        {
            "submodules": [
                {
                    "name": "app",
                    "path": "missing",
                    "manifest": "missing/structure.yml",
                    "summary": "App",
                }
            ]
        },
    ],
)
def test_broken_references(repo, update):
    data = manifest() | deepcopy(update)
    write(repo, "structure.yml", data)
    assert "does not exist" in "\n".join(VALIDATE(repo)[0])


@pytest.mark.parametrize("parent", [None, "missing.yml", "structure.yml"])
def test_missing_or_wrong_parent(repo, parent):
    link_child(repo)
    write(repo, "app/structure.yml", manifest("app", parent))
    assert "parent" in "\n".join(VALIDATE(repo)[0])


def test_unreachable_manifest(repo):
    write(repo, "orphan/structure.yml", manifest("orphan", "../structure.yml"))
    assert "unreachable" in "\n".join(VALIDATE(repo)[0])


def test_duplicate_child_and_incorrect_manifest_location(repo):
    data = link_child(repo)
    data["submodules"] *= 2
    write(repo, "structure.yml", data)
    assert "duplicate child" in "\n".join(VALIDATE(repo)[0])
    data["submodules"] = [data["submodules"][0] | {"manifest": "structure.yml"}]
    write(repo, "structure.yml", data)
    assert "must be path/structure.yml" in "\n".join(VALIDATE(repo)[0])


def test_multiple_callers_and_cycles_are_rejected(repo):
    data = link_child(repo)
    data["submodules"].append(
        {
            "name": "nested",
            "path": "app/nested",
            "manifest": "app/nested/structure.yml",
            "summary": "Nested",
        }
    )
    write(repo, "structure.yml", data)
    child = manifest("app", "../structure.yml")
    child["submodules"] = [
        {
            "name": "nested",
            "path": "nested",
            "manifest": "nested/structure.yml",
            "summary": "Nested",
        }
    ]
    write(repo, "app/structure.yml", child)
    nested = manifest("app/nested", "../structure.yml")
    write(repo, "app/nested/structure.yml", nested)
    assert "exactly one caller" in "\n".join(VALIDATE(repo)[0])
    child["submodules"] = [
        {
            "name": "root",
            "path": "..",
            "manifest": "../structure.yml",
            "summary": "Cycle",
        }
    ]
    write(repo, "app/structure.yml", child)
    assert "strict descendant" in "\n".join(VALIDATE(repo)[0])


@pytest.mark.parametrize("path", ["../outside", "/etc/passwd"])
def test_path_escape_and_absolute_paths(repo, path):
    data = manifest() | {"files": [path]}
    write(repo, "structure.yml", data)
    assert VALIDATE(repo)[0]


def test_symlink_escape(repo, tmp_path):
    (repo / "outside").symlink_to(tmp_path.parent)
    write(repo, "structure.yml", manifest() | {"files": ["outside"]})
    assert "escapes repository" in "\n".join(VALIDATE(repo)[0])


@pytest.mark.parametrize(
    "content", ["[", "[]", "version: 1\nversion: 2\n", "? [a, b]\n: value\n"]
)
def test_malformed_or_ambiguous_yaml(repo, content):
    (repo / "structure.yml").write_text(content)
    assert VALIDATE(repo)[0]


def test_git_scope_includes_new_manifests_and_ignores_artifacts(repo):
    (repo / ".gitignore").write_text(".venv/\nnode_modules/\nbuild/\nmedia/\n")
    for name in (".venv", "node_modules", "build", "media"):
        write(repo, f"{name}/structure.yml", {})
    assert VALIDATE(repo) == ([], 1)
    write(repo, "new/structure.yml", manifest("new", "../structure.yml"))
    assert "unreachable" in "\n".join(VALIDATE(repo)[0])


def test_deleted_tracked_manifest_is_drift(repo):
    link_child(repo)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    (repo / "app/structure.yml").unlink()
    assert "cannot load manifest" in "\n".join(VALIDATE(repo)[0])


def test_cli_fails_for_missing_root_and_passes_from_other_directory(repo):
    runner = ROOT / "scripts/lint_structure.py"
    result = subprocess.run(
        [sys.executable, str(runner)], cwd=repo, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    (repo / "structure.yml").unlink()
    result = subprocess.run(
        [sys.executable, str(runner), "--root", str(repo)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "root manifest" in result.stderr
