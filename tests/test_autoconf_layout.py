import ast
from pathlib import Path
from typing import Any, cast

from lx_administration.autoconf.layout import (
    AnsibleInventoryLayout,
    AutoconfOutputLayout,
    AutoconfSourceLayout,
    NixOutputLayout,
    NixTemplateLayout,
)
from lx_administration.yaml import load_unique_yaml_file

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_MAP = REPO_ROOT / "tests/autoconf.yml"


def _yaml_mapping(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], load_unique_yaml_file(path))


def _test_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def test_autoconf_test_map_is_complete_and_unambiguous() -> None:
    manifest = _yaml_mapping(TEST_MAP)
    project_map = _yaml_mapping(REPO_ROOT / "luxnix.yml")
    suites = manifest["suites"]
    suite_ids = [suite["id"] for suite in suites]
    suite_paths = [suite["path"] for suite in suites]
    discovered_paths = {
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "tests").glob("test_autoconf_*.py")
    }
    discovered_paths.add("tests/test_ansible_autoconf_nixos_config.py")

    assert manifest["schema_version"] == 1
    assert project_map["paths"]["autoconf_test_map"] == "tests/autoconf.yml"
    assert (REPO_ROOT / manifest["support"]).is_file()
    assert len(suite_ids) == len(set(suite_ids))
    assert len(suite_paths) == len(set(suite_paths))
    assert set(suite_paths) == discovered_paths

    owners: dict[str, str] = {}
    for suite in suites:
        path = REPO_ROOT / suite["path"]
        assert path.is_file()
        assert suite["scope"].strip()
        names = _test_names(path)
        assert names, f"{suite['id']}: suite must collect at least one test"
        for name in names:
            assert name not in owners, f"duplicate test name: {name}"
            owners[name] = suite["id"]


def test_autoconf_output_layout_centralizes_fixed_artifact_paths() -> None:
    output_root = Path("/tmp/luxnix-autoconf-output")
    layout = AutoconfOutputLayout(output_root)

    assert layout.inventory_file == output_root / "inventory.yml"
    assert layout.system_vars_dir == output_root / "merged_vars"
    assert layout.home_vars_dir == output_root / "home_merged_vars"
    assert layout.log_dir == output_root / "logs"


def test_autoconf_source_layout_centralizes_fixed_input_paths() -> None:
    ansible_root = Path("/tmp/luxnix-ansible")
    source = AutoconfSourceLayout(ansible_root)

    assert source.facts_dir == ansible_root / "cmdb"
    assert source.roles_dir == ansible_root / "roles"
    assert source.inventory == AnsibleInventoryLayout(ansible_root / "inventory")
    assert source.inventory.hosts_file == ansible_root / "inventory/hosts.ini"
    assert source.inventory.home_manifest == ansible_root / "inventory/home-hosts.yml"
    assert source.inventory.group_vars_dir == ansible_root / "inventory/group_vars"
    assert source.inventory.host_vars_dir == ansible_root / "inventory/host_vars"
    assert source.inventory.home_vars_dir == ansible_root / "inventory/host_vars/home"


def test_nix_layouts_centralize_template_and_output_paths() -> None:
    template_root = Path("/templates")
    output_root = Path("/generated")
    templates = NixTemplateLayout(template_root)
    outputs = NixOutputLayout(output_root)

    assert templates.systems_dir == template_root / "systems"
    assert templates.homes_dir == template_root / "homes"
    assert templates.system_template_dir("x86_64-linux", "main") == (
        template_root / "systems/x86_64-linux/main"
    )
    assert templates.home_template_dir("x86_64-linux") == (
        template_root / "homes/x86_64-linux"
    )
    assert outputs.system_file("x86_64-linux", "node-01") == (
        output_root / "systems/x86_64-linux/node-01/default.nix"
    )
    assert outputs.home_file("x86_64-linux", "operator", "node-01") == (
        output_root / "homes/x86_64-linux/operator@node-01/default.nix"
    )
