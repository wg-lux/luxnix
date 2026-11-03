"""Wheelhouse admission and target selection, without installing application code."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

from packaging.tags import Tag
import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "modules/nixos/services/lx-annotate-local/scripts/wheelhouse-lock.py"
)
spec = importlib.util.spec_from_file_location("wheelhouse_lock", SCRIPT)
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)


def application(tmp_path, version="1.7.3", dependencies=()):
    project = dict(
        name="lx-annotate",
        version=version,
        dependencies=list(dependencies),
        **{"requires-python": ">=3.12,<3.13"},
    )
    wheel = tmp_path / f"lx_annotate-{version}-py3-none-any.whl"
    metadata = f"Name: lx-annotate\nVersion: {version}\nRequires-Python: >=3.12,<3.13\n"
    metadata += "".join(f"Requires-Dist: {dependency}\n" for dependency in dependencies)
    # Optional project extras must not become required runtime dependencies.
    metadata += 'Requires-Dist: pytest>=9; extra == "dev"\n'
    with ZipFile(wheel, "w") as archive:
        archive.writestr(f"lx_annotate-{version}.dist-info/METADATA", metadata)
    return project, wheel


@pytest.mark.parametrize(
    "key,value",
    [
        ("version", "1.7.2"),
        ("dependencies", ["backend==2"]),
        ("requires-python", ">=3.13"),
        ("name", "other-app"),
    ],
)
def test_source_wheel_mismatch_is_rejected(tmp_path, key, value):
    project, wheel = application(tmp_path, dependencies=["backend[gpu]==1"])
    selection.validate_application(project, wheel)
    project[key] = value
    with pytest.raises(ValueError, match="does not match|do not match"):
        selection.validate_application(project, wheel)


def artifact(filename):
    return {"url": f"https://example.invalid/{filename}", "hash": "sha256:" + "a" * 64}


def package(name="backend", version="1"):
    return dict(
        name=name,
        version=version,
        source={"registry": "https://pypi.org/simple"},
        wheels=[artifact(f"{name}-{version}-py3-none-any.whl")],
    )


def test_production_export_controls_selection_and_platform_markers():
    backend = package()
    backend["wheels"].insert(
        0, artifact("backend-1-cp312-cp312-manylinux_2_17_x86_64.whl")
    )
    lock = {"package": [backend, package("gpu"), package("devtool")]}
    result = selection.select_artifacts(
        lock,
        'backend==1\ngpu==1; sys_platform == "linux"\n'
        'windows==1; sys_platform == "win32"',
        [Tag("cp312", "cp312", "manylinux_2_17_x86_64"), Tag("py3", "none", "any")],
    )
    assert [entry["name"] for entry in result] == ["backend", "gpu"]
    assert result[0]["filename"].endswith("manylinux_2_17_x86_64.whl")


def test_incompatible_wheel_uses_hash_pinned_source():
    dependency = package()
    dependency["wheels"] = [artifact("backend-1-cp313-cp313-win_amd64.whl")]
    dependency["sdist"] = artifact("backend-1.tar.gz")
    result = selection.select_artifacts(
        {"package": [dependency]}, "backend==1", [Tag("py3", "none", "any")]
    )
    assert result[0]["source"] is True
    assert result[0]["sha256"] == "a" * 64
    del dependency["sdist"]
    with pytest.raises(ValueError, match="No compatible wheel"):
        selection.select_artifacts(
            {"package": [dependency]}, "backend==1", [Tag("py3", "none", "any")]
        )


@pytest.mark.parametrize(
    "requirement",
    ["backend>=1", "backend==1.*", "backend @ https://example.invalid/a.whl"],
)
def test_unpinned_export_rejected(requirement):
    with pytest.raises(ValueError, match="Expected exact registry"):
        selection.select_artifacts({"package": [package()]}, requirement)


def test_missing_hash_and_ambiguous_lock_rejected():
    dependency = package()
    dependency["wheels"][0]["hash"] = "sha256:invalid"
    with pytest.raises(ValueError, match="Missing SHA256"):
        selection.select_artifacts({"package": [dependency]}, "backend==1")
    with pytest.raises(ValueError, match="Expected one registry"):
        selection.select_artifacts({"package": [dependency, dependency]}, "backend==1")


def test_real_uv_rejects_stale_pyproject_lock_pair(tmp_path):
    assert shutil.which("uv"), "uv is required for the lock validation contract"
    project, wheel = application(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        + "\n".join(f"{key} = {json.dumps(value)}" for key, value in project.items())
    )
    subprocess.run(
        [
            "uv",
            "lock",
            "--project",
            str(tmp_path),
            "--offline",
            "--python",
            sys.executable,
            "--no-python-downloads",
        ],
        check=True,
        capture_output=True,
    )
    command = [sys.executable, str(SCRIPT), str(tmp_path), str(wheel)]
    good = subprocess.run(command, text=True, capture_output=True)
    assert good.returncode == 0, good.stderr
    assert json.loads(good.stdout)["artifacts"] == []
    # Keep wheel/source parity, but change a dependency without updating uv.lock.
    project, wheel = application(tmp_path, dependencies=["missing-package==1"])
    pyproject.write_text(
        "[project]\n"
        + "\n".join(f"{key} = {json.dumps(value)}" for key, value in project.items())
    )
    bad = subprocess.run(command, text=True, capture_output=True)
    assert bad.returncode != 0
    assert not bad.stdout
