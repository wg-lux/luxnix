from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
LAYOUT = REPO_ROOT / "tests/layout.yml"


def _layout() -> dict[str, Any]:
    return yaml.safe_load(LAYOUT.read_text(encoding="utf-8"))


def test_test_layout_declares_existing_owned_entrypoints() -> None:
    layout = _layout()

    assert layout["schema_version"] == 1
    assert layout["pytest_root"] == "tests"
    assert layout["pytest_command"] == "uv run pytest -q"

    entries = (
        layout["python_suites"]
        + layout["nix_suites"]
        + layout["independent_projects"]
    )
    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids))

    for entry in entries:
        path = REPO_ROOT / entry["path"]
        assert path.exists(), entry["id"]
        assert entry["scope"].strip(), entry["id"]
        assert entry["command"].strip(), entry["id"]


def test_default_pytest_configuration_excludes_nested_project_tests() -> None:
    config = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "[tool.pytest.ini_options]" in config
    assert 'testpaths = ["tests"]' in config
    assert "wg-lux-mcp" not in config
