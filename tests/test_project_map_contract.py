from __future__ import annotations

from pathlib import Path
import re
import subprocess
from typing import Any, cast

from lx_administration.yaml import load_unique_yaml_file

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_MAP_PATH = REPO_ROOT / "luxnix.yml"


def _yaml_mapping(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], load_unique_yaml_file(path))


def _project_map() -> dict[str, Any]:
    return _yaml_mapping(PROJECT_MAP_PATH)


def test_project_map_points_to_live_or_explicitly_local_paths() -> None:
    project_map = _project_map()
    paths = project_map["paths"]
    lifecycle = project_map["path_lifecycle"]

    assert set(lifecycle) <= set(paths)
    for path_id, relative_path in paths.items():
        artifact = REPO_ROOT / relative_path
        metadata = lifecycle.get(path_id)
        if metadata is None:
            assert artifact.exists(), f"paths.{path_id} is missing: {relative_path}"
        elif metadata.get("may_be_missing"):
            assert (
                artifact.parent.is_dir()
            ), f"paths.{path_id} parent is missing: {artifact.parent}"
        else:
            assert artifact.exists(), f"paths.{path_id} is missing: {relative_path}"


def test_local_project_map_paths_are_declared_and_gitignored() -> None:
    project_map = _project_map()
    paths = project_map["paths"]
    lifecycle = project_map["path_lifecycle"]

    assert lifecycle["local_ansible_facts"] == {
        "state": "local-sensitive",
        "gitignored": True,
        "may_be_empty": True,
        "refresh_command": "devenv tasks run autoconf:refresh-facts",
    }
    assert lifecycle["local_inventory_report"] == {
        "state": "generated-local",
        "gitignored": True,
        "may_be_missing": True,
        "generate_command": "devenv tasks run autoconf:generate-report",
    }

    ignored_examples = [
        Path(paths["local_ansible_facts"]) / "example.json",
        Path(paths["local_inventory_report"]),
    ]
    for ignored_path in ignored_examples:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", ignored_path],
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0, f"not gitignored: {ignored_path}"


def test_project_map_workflows_have_stable_safe_metadata() -> None:
    project_map = _project_map()
    workflows = project_map["workflows"]
    workflow_ids = [workflow["id"] for workflow in workflows]
    risk_levels = project_map["risk_levels"]

    assert project_map["schema_version"] == 1
    assert all(description.strip() for description in risk_levels.values())
    assert len(workflow_ids) == len(set(workflow_ids))
    for workflow in workflows:
        assert workflow["summary"].strip()
        assert workflow["command"].strip()
        assert workflow["risk"] in risk_levels

        if workflow["risk"].endswith("state") or workflow["risk"].startswith(
            "destructive-"
        ):
            assert workflow.get("effects"), f"{workflow['id']} must document effects"
        if workflow["risk"].startswith("destructive-"):
            assert workflow.get("confirmation_required") is True
        if workflow["command"].startswith("devenv "):
            assert "devenv" in workflow.get("prerequisites", [])

        documentation = workflow["documentation"]
        assert documentation.startswith("docs/")
        assert (REPO_ROOT / documentation).is_file()

        for argument in workflow.get("arguments", {}).values():
            source = argument["source"]
            assert source == "operator" or source in workflow_ids


def test_project_map_support_links_are_local_files() -> None:
    project_map = _project_map()
    paths = project_map["paths"]
    support = project_map["support"]
    local_links = {
        project_map["project"]["start_here"],
        project_map["project"]["contributor_guidance"],
        *support.values(),
    }

    assert all((REPO_ROOT / relative_path).is_file() for relative_path in local_links)
    assert support["documentation_home"] == paths["documentation_home"]
    assert support["command_catalog"] == paths["development_command_catalog"]
    assert support["inventory_variables"] == paths["inventory_variable_guide"]
    assert support["nix_generation_templates"] == paths["nix_generation_template_guide"]


def test_project_map_names_autoconf_template_ownership() -> None:
    project_map = _project_map()
    paths = project_map["paths"]
    canonical_sources = project_map["artifact_ownership"]["autoconf"][
        "canonical_sources"
    ]

    assert paths["nix_generation_templates"] in canonical_sources
    assert Path(paths["nix_generation_template_guide"]).parent == Path(
        paths["nix_generation_templates"]
    )


def test_project_map_exposes_active_top_level_implementation_roots() -> None:
    paths = _project_map()["paths"]

    assert {
        key: paths[key]
        for key in (
            "python_package",
            "snowfall_library",
            "nix_packages",
            "nix_overlays",
            "development_shells",
            "kubernetes_manifests",
            "topology_module",
            "tmux_configuration",
        )
    } == {
        "python_package": "lx_administration",
        "snowfall_library": "lib",
        "nix_packages": "packages",
        "nix_overlays": "overlays",
        "development_shells": "shells",
        "kubernetes_manifests": "kubernetes",
        "topology_module": "topology/default.nix",
        "tmux_configuration": "tmux",
    }


def test_manual_operation_templates_are_explicitly_classified() -> None:
    project_map = _project_map()
    catalog_path = REPO_ROOT / project_map["paths"]["manual_operation_catalog"]
    catalog = _yaml_mapping(catalog_path)
    operations = catalog["operations"]
    workflow_ids = {workflow["id"] for workflow in project_map["workflows"]}

    assert project_map["support"]["manual_operations"] == str(
        catalog_path.relative_to(REPO_ROOT)
    )
    assert catalog["schema_version"] == 1
    assert catalog["risk_levels_source"] == "../luxnix.yml#risk_levels"
    assert catalog["canonical_workflows_source"] == "../luxnix.yml#workflows"
    assert {operation["path"] for operation in operations} == {
        "scripts/hetzner-dedicated-wipe-and-install-nixos.sh",
        "scripts/recover-files-live-boot.sh",
    }

    for operation in operations:
        script = REPO_ROOT / operation["path"]
        assert script.is_file()
        assert operation["status"] == "manual-template"
        assert operation["canonical"] is False
        assert operation["risk"] in project_map["risk_levels"]
        assert operation["risk"].startswith("destructive-")
        assert operation["review_required"]
        assert (REPO_ROOT / operation["guidance"]).is_file()
        assert "manual template" in script.read_text(encoding="utf-8")[:500]
        if safer_workflow := operation.get("safer_workflow"):
            assert safer_workflow in workflow_ids


def test_historical_autodocs_is_preserved_but_not_a_canonical_entry_point() -> None:
    project_map = _project_map()
    lifecycle = project_map["path_lifecycle"]["legacy_autodocs"]
    autodocs_dir = REPO_ROOT / project_map["paths"]["legacy_autodocs"]
    status = _yaml_mapping(REPO_ROOT / lifecycle["status_file"])
    workflow_ids = {workflow["id"] for workflow in project_map["workflows"]}

    assert lifecycle == {
        "state": "inactive-preserved",
        "canonical": False,
        "status_file": "autodocs/status.yml",
    }
    assert status["schema_version"] == 1
    assert status["status"] == lifecycle["state"]
    assert status["canonical"] is lifecycle["canonical"]
    assert (REPO_ROOT / status["entrypoint"]).is_file()
    assert not (REPO_ROOT / status["history"]["original_input"]).exists()
    assert status["blocked_by"]
    assert status["current_operator_report"]["workflow"] in workflow_ids
    assert status["current_operator_report"]["feature_equivalence"] == (
        "not-established"
    )
    assert "Preserve" in status["retention"]
    assert (
        "inactive preserved"
        in (autodocs_dir / "mermaid_report_of_host_configs.py").read_text(
            encoding="utf-8"
        )[:400]
    )


def test_topology_has_one_flake_imported_entry_point() -> None:
    project_map = _project_map()
    canonical = REPO_ROOT / project_map["paths"]["topology_module"]
    flake = (REPO_ROOT / "flake.nix").read_text(encoding="utf-8")
    topology_module = canonical.read_text(encoding="utf-8")

    assert canonical == REPO_ROOT / "topology/default.nix"
    assert canonical.is_file()
    assert "(import ./topology {" in flake
    assert "nixosConfigurations" in flake
    assert not (REPO_ROOT / "topology.nix").exists()
    for stale_static_claim in (
        "nodes.",
        "networks.",
        "server-03",
        "tailscale0",
        "192.168.1.1/24",
    ):
        assert stale_static_claim not in topology_module


def test_readme_structure_exposes_durable_project_map_roots() -> None:
    project_map = _project_map()
    lifecycle_paths = set(project_map["path_lifecycle"])
    durable_roots = {
        Path(relative_path).parts[0]
        for path_id, relative_path in project_map["paths"].items()
        if path_id not in lifecycle_paths
    }
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    structure = readme.split("## Repository Structure", 1)[1].split("```", 2)[1]

    assert "luxnix.yml" in structure
    assert all(root in structure for root in durable_roots)
    assert "cmdb/" not in structure
    assert "autodocs/" not in structure


def test_readme_start_here_has_only_canonical_role_based_entry_points() -> None:
    project_map = _project_map()
    paths = project_map["paths"]
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    start_here = readme.split("## Start Here", 1)[1].split("## Quick Start", 1)[0]
    targets = re.findall(r"\[[^]]+\]\(([^)]+)\)", start_here)
    expected_targets = {
        project_map["project"]["start_here"],
        paths["documentation_home"],
        paths["documentation_index"],
        paths["development_command_catalog"],
        PROJECT_MAP_PATH.name,
    }

    assert len(targets) == len(set(targets))
    assert set(targets) == expected_targets
    for goal in (
        "Set up or deploy a host",
        "Browse operator and contributor guides",
        "Inspect paths, workflows, commands, and risks as data",
    ):
        assert goal in start_here


def test_readme_quick_start_matches_central_host_workflows() -> None:
    workflows = {workflow["id"]: workflow for workflow in _project_map()["workflows"]}
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme.split("## Quick Start", 1)[1].split(
        "Agents and automation", 1
    )[0]
    ordered_workflows = (
        "discover-hosts",
        "validate-host",
        "build-host",
        "check-connectivity",
        "deploy-new-host",
    )

    command_positions = [
        quick_start.index(workflows[workflow_id]["command"])
        for workflow_id in ordered_workflows
    ]
    assert command_positions == sorted(command_positions)
    assert "repartition" in quick_start
    assert "<ip>" not in quick_start


def test_host_setup_guides_match_central_host_file_conventions() -> None:
    conventions = _project_map()["host_conventions"]
    guides = {
        relative_path: (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in (
            "docs/hardware-setup.md",
            "docs/deployment-guide.md",
        )
    }

    for guide in guides.values():
        normalized_guide = " ".join(guide.split())
        for required_file in conventions["required_system_files"]:
            assert required_file in guide
        for convention_group in (
            "conditional_system_files",
            "conditional_generated_outputs",
        ):
            for conditional_file, condition in conventions[convention_group].items():
                assert conditional_file in guide
                assert condition in normalized_guide

    hardware_guide = guides["docs/hardware-setup.md"]
    assert "only file required for every exported host" in " ".join(
        hardware_guide.split()
    )
    assert "It is a generated output" in hardware_guide
    assert "Only the adjacent hardware files" in hardware_guide
    assert "UEFI-capable system" not in hardware_guide


def test_host_conventions_separate_generated_outputs_from_adjacent_files() -> None:
    project_map = _project_map()
    conventions = project_map["host_conventions"]
    generated_outputs = set(
        project_map["artifact_ownership"]["autoconf"]["generated_outputs"]
    )

    assert set(conventions["conditional_system_files"]) == {
        "disks.nix",
        "hardware-configuration.nix",
    }
    assert set(conventions["conditional_generated_outputs"]) <= generated_outputs
    assert "conditional_files" not in conventions


def test_new_host_guide_uses_canonical_autoconf_inputs() -> None:
    project_map = _project_map()
    guide = (REPO_ROOT / "docs/deployment-guide.md").read_text(encoding="utf-8")

    for path_id in ("remote_inventory", "home_inventory"):
        assert project_map["paths"][path_id] in guide
    for source in (
        "ansible/inventory/group_vars/",
        "ansible/inventory/host_vars/",
    ):
        assert source in guide

    assert "devenv tasks run autoconf:check" in guide
    assert "devenv tasks run autoconf:generate" in guide
    assert "Ensure these files exist" not in guide


def test_superseded_documentation_has_one_live_canonical_replacement() -> None:
    replacements = _project_map()["documentation_replacements"]

    for obsolete, canonical in replacements.items():
        assert not (
            REPO_ROOT / obsolete
        ).exists(), f"obsolete guide still exists: {obsolete}"
        assert (REPO_ROOT / canonical).is_file(), f"missing replacement for {obsolete}"


def test_legacy_nix_manager_implementation_is_removed():
    assert not (REPO_ROOT / "lx_administration/nix_manager").exists()


def test_autoconf_documentation_names_only_live_configuration_sources():
    template_docs = (REPO_ROOT / "conf/nix-templates/readme.md").read_text()
    pipeline_docs = (REPO_ROOT / "docs/autoconf.md").read_text()

    assert not (REPO_ROOT / "conf/_nix-configs").exists()
    assert not (REPO_ROOT / "lx_administration/ansible/hostinfo.py").exists()
    assert "conf/_nix-configs" not in template_docs
    assert "conf/_nix-configs" not in pipeline_docs
    assert "ansible/inventory/host_vars/<host>.yml" in template_docs
    assert (
        "conf/nix-templates/systems/x86_64-linux/main/default.nix.j2" in template_docs
    )
    assert "conf/nix-templates/homes/x86_64-linux/default.nix.j2" in template_docs
    assert "ansible/inventory/group_vars/README.md" in template_docs
