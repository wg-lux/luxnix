from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
LOCAL_LINK = re.compile(r"(?<!!)\[[^]]*\]\(([^)]+)\)")


class MkDocsLoader(yaml.SafeLoader):
    """Safe YAML loader that preserves MkDocs Python-name references as text."""


MkDocsLoader.add_multi_constructor(
    "tag:yaml.org,2002:python/name:",
    lambda _loader, suffix, _node: suffix,
)


def _nav_targets(items: list[Any]) -> Iterator[str]:
    for item in items:
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            for value in item.values():
                if isinstance(value, str):
                    yield value
                elif isinstance(value, list):
                    yield from _nav_targets(value)


def _documentation_files() -> list[Path]:
    module_docs = [
        REPO_ROOT / "modules/nixos/roles/managed-secrets/README.md",
        REPO_ROOT / "modules/nixos/luxnix/generic-settings/readme.md",
        *(REPO_ROOT / "modules/nixos/services/lx-annotate-local").glob("*.md"),
    ]
    return sorted(DOCS_DIR.glob("*.md")) + sorted(module_docs)


def _matches_exclude_pattern(target: str, pattern: str) -> bool:
    return target.startswith(pattern) if pattern.endswith("/") else target == pattern


def _normalized_markdown_commands(content: str) -> str:
    """Flatten prose and shell continuations for command contract checks."""
    return " ".join(content.replace("\\\n", " ").split())


def test_mkdocs_navigation_targets_existing_unique_pages() -> None:
    config = yaml.load(
        (REPO_ROOT / "mkdocs.yaml").read_text(encoding="utf-8"),
        Loader=MkDocsLoader,
    )
    targets = list(_nav_targets(config["nav"]))
    all_pages = {str(path.relative_to(DOCS_DIR)) for path in DOCS_DIR.rglob("*.md")}
    exclude_patterns = {
        line.strip()
        for line in config.get("exclude_docs", "").splitlines()
        if line.strip()
    }
    excluded_pages = {
        page
        for page in all_pages
        if any(_matches_exclude_pattern(page, pattern) for pattern in exclude_patterns)
    }

    assert targets
    assert len(targets) == len(set(targets)), "MkDocs navigation contains duplicates"
    assert not [target for target in targets if not (DOCS_DIR / target).is_file()]
    assert not set(targets) & excluded_pages
    assert all_pages == set(targets) | excluded_pages, (
        "Every Markdown page must be navigated or explicitly excluded"
    )

    escaping_links = {
        f"{target}: {link}"
        for target in targets
        for link in LOCAL_LINK.findall((DOCS_DIR / target).read_text(encoding="utf-8"))
        if link.strip().split()[0].strip("<>").startswith("../")
    }
    assert not escaping_links, "MkDocs pages link outside docs_dir:\n" + "\n".join(
        sorted(escaping_links)
    )


def test_documentation_uses_valid_portable_local_links() -> None:
    invalid: list[str] = []
    for document in _documentation_files():
        for raw_target in LOCAL_LINK.findall(document.read_text(encoding="utf-8")):
            target = raw_target.strip().split()[0].strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if target.startswith("/"):
                invalid.append(f"{document}: absolute local link {target}")
                continue

            local_target = target.split("#", 1)[0]
            if local_target and not (document.parent / local_target).resolve().exists():
                invalid.append(f"{document}: missing local link {target}")

    assert not invalid, "\n".join(invalid)


def test_documentation_home_has_unique_task_oriented_links() -> None:
    home = DOCS_DIR / "index.md"
    home_text = home.read_text(encoding="utf-8")
    local_targets = [
        target
        for raw_target in LOCAL_LINK.findall(home_text)
        if not (target := raw_target.strip().split()[0].strip("<>")).startswith(
            ("http://", "https://", "mailto:", "#")
        )
    ]

    assert len(local_targets) == len(set(local_targets))
    for heading in (
        "## Start here",
        "## Operations",
        "## Service engineering",
        "## Implementation plans",
        "## Troubleshooting",
    ):
        assert heading in home_text

    assert "/luxnix.yml" in home_text
    assert "/devenv/commands.yml" in home_text


def test_support_map_is_reachable_from_human_documentation_homes() -> None:
    project_map = yaml.safe_load((REPO_ROOT / "luxnix.yml").read_text())
    documents = (REPO_ROOT / "README.md", DOCS_DIR / "index.md")
    linked_targets = {"docs/index.md"}

    for document in documents:
        for raw_target in LOCAL_LINK.findall(document.read_text(encoding="utf-8")):
            target = raw_target.strip().split()[0].strip("<>").split("#", 1)[0]
            github_prefix = "https://github.com/wg-lux/luxnix/blob/main/"
            if target.startswith(github_prefix):
                linked_targets.add(target.removeprefix(github_prefix))
            elif not target.startswith(("http://", "https://", "mailto:")):
                resolved = (document.parent / target).resolve()
                if resolved.is_relative_to(REPO_ROOT):
                    linked_targets.add(str(resolved.relative_to(REPO_ROOT)))

    assert set(project_map["support"].values()) <= linked_targets


def test_machine_support_map_exposes_human_and_agent_entry_points() -> None:
    project_map = yaml.safe_load((REPO_ROOT / "luxnix.yml").read_text())
    paths = project_map["paths"]
    support = project_map["support"]

    assert support["documentation_home"] == paths["documentation_home"]
    assert support["command_catalog"] == paths["development_command_catalog"]
    assert support["inventory_variables"] == paths["inventory_variable_guide"]
    assert support["nix_generation_templates"] == paths["nix_generation_template_guide"]
    assert support["vault_hub_enrollment"] == ("docs/vault-hub-machine-enrollment.md")


def test_network_docs_use_inventory_as_the_single_topology_source() -> None:
    architecture = (DOCS_DIR / "network-architecture.md").read_text(encoding="utf-8")
    topology = yaml.safe_load(
        (DOCS_DIR / "network-topology.yaml").read_text(encoding="utf-8")
    )
    project_map = yaml.safe_load((REPO_ROOT / "luxnix.yml").read_text())

    assert topology["status"] == "derived-source-map"
    assert topology["canonical_sources"]["hosts_groups_and_vpn_addresses"] == (
        "ansible/inventory/hosts.ini"
    )
    assert "Clients" not in topology
    assert "Permissions" not in topology
    assert "vpn_ip" not in topology

    for source in topology["canonical_sources"].values():
        assert (REPO_ROOT / source).exists()
        assert source in architecture

    assert "./network-resolution.md" in architecture
    assert "./network-topology.yaml" in architecture
    for stale_claim in ("homelab.haseebmajid.dev", "vpn.luxnix.org", "Tailscale"):
        assert stale_claim not in architecture

    assert project_map["paths"]["network_topology_map"] == (
        "docs/network-topology.yaml"
    )
    assert project_map["support"]["network_architecture"] == (
        "docs/network-architecture.md"
    )
    assert project_map["support"]["network_resolution"] == (
        "docs/network-resolution.md"
    )
    assert topology["visualization"] == {
        "entrypoint": "topology/default.nix",
        "source": "flake.nix nixosConfigurations",
        "rule": "Do not duplicate static hosts or networks in the topology module.",
    }
    assert "topology/default.nix" in architecture
    assert "nixosConfigurations" in architecture

    resolution = (DOCS_DIR / "network-resolution.md").read_text(encoding="utf-8")
    assert "publicDomainSuffixes" in resolution
    assert "publicDnsDomains" not in resolution


def test_project_workflow_guides_are_in_mkdocs_navigation() -> None:
    project_map = yaml.safe_load((REPO_ROOT / "luxnix.yml").read_text())
    config = yaml.load(
        (REPO_ROOT / "mkdocs.yaml").read_text(encoding="utf-8"),
        Loader=MkDocsLoader,
    )
    navigated_pages = set(_nav_targets(config["nav"]))
    workflow_guides = {
        workflow["documentation"].removeprefix("docs/")
        for workflow in project_map["workflows"]
    }

    assert workflow_guides <= navigated_pages
    for workflow in project_map["workflows"]:
        guide = _normalized_markdown_commands(
            (REPO_ROOT / workflow["documentation"]).read_text(encoding="utf-8")
        )
        assert " ".join(workflow["command"].split()) in guide
        if strict_command := workflow.get("strict_command"):
            assert " ".join(strict_command.split()) in guide


def test_autoconf_guide_exposes_every_central_autoconf_command() -> None:
    project_map = yaml.safe_load((REPO_ROOT / "luxnix.yml").read_text())
    guide = (DOCS_DIR / "autoconf.md").read_text(encoding="utf-8")
    workflows = [
        workflow
        for workflow in project_map["workflows"]
        if workflow["documentation"] == "docs/autoconf.md"
    ]

    assert workflows
    for workflow in workflows:
        assert workflow["command"] in guide
        if strict_command := workflow.get("strict_command"):
            assert strict_command in guide


def test_autoconf_guide_documents_script_option_lookup() -> None:
    guide = (DOCS_DIR / "autoconf.md").read_text(encoding="utf-8")

    assert (
        "python scripts/autoconf-pipeline.py --print-option paths.ansible_root" in guide
    )
    assert "does not require configured source paths to exist" in guide
    assert "`--check` when the complete source and output layout" in guide


def test_autoconf_guide_explains_first_run_output_creation() -> None:
    guide = (DOCS_DIR / "autoconf.md").read_text(encoding="utf-8")

    assert "`paths.nix_output` is a generated destination" in guide
    assert "does not need to exist before" in guide
    assert "creates the required system and Home Manager parent" in guide


def test_autoconf_guide_explains_optional_local_fact_snapshots() -> None:
    guide = (DOCS_DIR / "autoconf.md").read_text(encoding="utf-8")

    assert "directory is optional for an initial run" in guide
    assert "Autoconf continues" in guide
    assert "without hardware facts" in guide
    assert "fact-refresh command creates it" in guide


def test_autoconf_guide_points_to_the_canonical_test_map() -> None:
    guide = (DOCS_DIR / "autoconf.md").read_text(encoding="utf-8")
    project_map = yaml.safe_load((REPO_ROOT / "luxnix.yml").read_text())
    test_map = project_map["paths"]["autoconf_test_map"]

    assert test_map == "tests/autoconf.yml"
    assert test_map in guide
    assert f"https://github.com/wg-lux/luxnix/blob/main/{test_map}" in guide
    assert "lx_administration/autoconf/" in guide
    assert "pytest -q tests/test_autoconf_*.py" in guide


def test_autoconf_guide_explains_system_only_home_sources() -> None:
    guide = (DOCS_DIR / "autoconf.md").read_text(encoding="utf-8")

    assert "For a system-only setup" in guide
    assert "`home-hosts.yml` may contain `hosts: {}`" in guide
    assert "both `host_vars/home/`" in guide
    assert "`conf/nix-templates/homes/` template subtree may be absent" in guide
    assert "validates their host files and platform templates" in guide


def test_repository_toc_matches_canonical_mkdocs_navigation() -> None:
    generator = REPO_ROOT / "lib/toc-generator/generate-toc.py"
    result = subprocess.run(
        [sys.executable, generator, "--check"],
        cwd="/tmp",
        check=False,
        capture_output=True,
        text=True,
    )
    toc = (REPO_ROOT / "TABLE_OF_CONTENTS.md").read_text(encoding="utf-8")
    targets = list(
        _nav_targets(
            yaml.load(
                (REPO_ROOT / "mkdocs.yaml").read_text(encoding="utf-8"),
                Loader=MkDocsLoader,
            )["nav"]
        )
    )

    assert result.returncode == 0, result.stderr
    assert "Generated from mkdocs.yaml" in toc
    assert all(f"(docs/{target})" in toc for target in targets)
    assert "Luxnix_Setup.excalidraw.md" not in toc
    assert "[Documentation Map](TABLE_OF_CONTENTS.md)" in (
        REPO_ROOT / "README.md"
    ).read_text(encoding="utf-8")


def test_superseded_root_guides_do_not_compete_with_canonical_documentation() -> None:
    project_map = yaml.safe_load((REPO_ROOT / "luxnix.yml").read_text())
    replacements = project_map["documentation_replacements"]

    assert not (REPO_ROOT / "DEADCODE.md").exists()
    for obsolete, canonical in replacements.items():
        assert not (REPO_ROOT / obsolete).exists()
        assert (REPO_ROOT / canonical).is_file()

    cluster_review = REPO_ROOT / replacements["cluster.md"]
    assert cluster_review.is_file()
    assert (REPO_ROOT / "kubernetes/lx-annotate").is_dir()

    required_operator_contracts = {
        "docs/autoconf.md": (
            "autoconf:refresh-facts-strict",
            "last-known-good",
            "autoconf:generate-report",
        ),
        "docs/database-ownership.md": (
            "roles.endoreg-client.database",
            "postgres-endoreg-setup.service",
        ),
        "docs/development.md": (
            "ansible/inventory/host_vars/home/<host>.yml",
            "devenv tasks run autoconf:generate",
            "Do not hand-edit generated files",
        ),
        "docs/deploying-services-lx-annotate-style.md": (
            "vault-auth-setup.service",
            "managed-secrets-setup.service",
        ),
        "docs/lx-annotate-cluster-readiness.md": (
            "## Required Release Flow",
            "## Remaining Gates",
        ),
        "docs/vault-setup.md": (
            "vault-bootstrap",
            "validate-admin-passwords",
        ),
    }
    for canonical, required_texts in required_operator_contracts.items():
        content = (REPO_ROOT / canonical).read_text(encoding="utf-8")
        assert all(required in content for required in required_texts)

    development = (REPO_ROOT / "docs/development.md").read_text(encoding="utf-8")
    assert development.count("```") % 2 == 0
    assert "TODO" not in development

    allowed_root_markdown = {
        "AGENTS.md",
        "CommonErrors.md",
        "LxCheatsheet.md",
        "README.md",
        "TABLE_OF_CONTENTS.md",
    }
    assert {path.name for path in REPO_ROOT.glob("*.md")} == allowed_root_markdown


def test_documented_devenv_commands_use_current_cli_entry_points() -> None:
    documented_files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CommonErrors.md",
        REPO_ROOT / "LxCheatsheet.md",
        REPO_ROOT / "conf/nix-templates/readme.md",
        *DOCS_DIR.glob("*.md"),
    ]
    stale_commands = [
        str(path)
        for path in documented_files
        if "devenv run " in path.read_text(encoding="utf-8")
    ]

    assert not stale_commands
    assert "devenv shell vault-bootstrap" in (DOCS_DIR / "vault-setup.md").read_text(
        encoding="utf-8"
    )
    project_map = (REPO_ROOT / "luxnix.yml").read_text(encoding="utf-8")
    assert "devenv run " not in project_map
    assert "devenv shell vault-bootstrap" in project_map

    documented_scripts = {
        match
        for path in documented_files
        for match in re.findall(
            r"\bdevenv shell ([a-z][a-z0-9-]*)",
            path.read_text(encoding="utf-8"),
        )
    }
    script_definitions = "\n".join(
        (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in ("devenv/scripts.nix", "devenv/management.nix")
    )
    missing_scripts = {
        name for name in documented_scripts if f"{name}.exec" not in script_definitions
    }
    assert not missing_scripts
    direct_connectivity_references = [
        str(path)
        for path in documented_files
        if "./scripts/check-connectivity.sh" in path.read_text(encoding="utf-8")
    ]
    assert not direct_connectivity_references


def test_cheatsheet_routes_agents_to_safe_canonical_commands() -> None:
    cheatsheet = (REPO_ROOT / "LxCheatsheet.md").read_text(encoding="utf-8")

    assert "[command catalog](devenv/commands.yml)" in cheatsheet
    assert "[project map](luxnix.yml)" in cheatsheet
    for target in ("devenv/commands.yml", "luxnix.yml"):
        assert (REPO_ROOT / target).is_file()
    assert cheatsheet.index("autoconf:check") < cheatsheet.index("autoconf:generate")
    assert "run-ansible --check --diff --limit <host-or-group>" in cheatsheet
    assert "sync-secrets --limit <host-or-group>" in cheatsheet
    assert "reject an omitted or empty `--limit`" in cheatsheet
    assert "--limit all" in cheatsheet


def test_common_errors_repairs_autoconf_sources_instead_of_outputs() -> None:
    errors = (REPO_ROOT / "CommonErrors.md").read_text(encoding="utf-8")

    assert "[project map](luxnix.yml)" in errors
    assert "[command catalog](devenv/commands.yml)" in errors
    for target in (
        "luxnix.yml",
        "devenv/commands.yml",
        "ansible/inventory/home-hosts.yml",
        "ansible/inventory/host_vars/home",
    ):
        assert (REPO_ROOT / target).exists()
    assert "ansible/inventory/home-hosts.yml" in errors
    assert "ansible/inventory/host_vars/home/<host>.yml" in errors
    assert "Home-only host" in errors
    assert "Add `homes/x86_64-linux/admin@<host>/default.nix`" not in errors
    assert "matching host exists under `systems/" not in errors
    assert "run-ansible --check --diff --limit <host-or-group>" in errors
    assert "sync-secrets --limit <host-or-group>" in errors
    assert "return Exit 2 locally" in errors


def test_day_zero_guides_generate_from_inventory_before_preflight() -> None:
    guides = {
        relative_path: (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in (
            "docs/getting-started.md",
            "docs/deployment-guide.md",
        )
    }

    for guide in guides.values():
        for source in (
            "ansible/inventory/hosts.ini",
            "ansible/inventory/home-hosts.yml",
            "ansible/inventory/group_vars/",
            "ansible/inventory/host_vars/<host>.yml",
            "ansible/inventory/host_vars/home/<host>.yml",
        ):
            assert source in guide

        check_position = guide.index("devenv tasks run autoconf:check")
        generate_position = guide.index("devenv tasks run autoconf:generate")
        validate_position = guide.index("config.system.build.toplevel")
        assert check_position < generate_position < validate_position
        assert "without editing them directly" in guide or (
            "do not edit either output directly" in guide
        )

        for stale_instruction in (
            "Choose an existing host from `systems/x86_64-linux/` or create a new one",
            "Ensure `systems/x86_64-linux/<host>/default.nix` exists",
            "Add `homes/x86_64-linux/admin@<host>/default.nix`",
        ):
            assert stale_instruction not in guide


def test_secret_bootstrap_creates_its_gitignored_parent_directory() -> None:
    getting_started = (DOCS_DIR / "getting-started.md").read_text(encoding="utf-8")
    deployment = (DOCS_DIR / "deployment-guide.md").read_text(encoding="utf-8")
    example = (REPO_ROOT / "ansible/admin-passwords.example.yml").read_text(
        encoding="utf-8"
    )

    assert "mkdir -p ansible/secrets" in getting_started
    assert "mkdir -p ansible/secrets" in deployment
    assert "mkdir -p ansible/secrets" in example


def test_secret_rotation_uses_the_canonical_vault_key_path() -> None:
    script = (REPO_ROOT / "scripts/update_secret.py").read_text(encoding="utf-8")
    guide = (DOCS_DIR / "vault-setup.md").read_text(encoding="utf-8")

    assert 'default="~/.lxv.key"' in script
    assert "~/.lsv.key" not in script
    assert "_bash =" not in script
    assert "--vault-key ~/.lxv.key" in guide


def test_architecture_maps_autoconf_sources_to_generated_outputs() -> None:
    architecture = (DOCS_DIR / "architecture.md").read_text(encoding="utf-8")

    for source in (
        "ansible/inventory/",
        "autoconf/config.yml",
        "conf/nix-templates/",
    ):
        assert source in architecture
    for generated in (
        "autoconf/inventory.yml",
        "systems/<platform>/<host>/default.nix",
        "homes/<platform>/<user>@<host>/default.nix",
    ):
        assert generated in architecture
    assert "derived output" in architecture
    assert "Nix generation templates" in architecture
    assert "host_nixos:" in architecture
    assert "host_roles:" in architecture
    assert "host_luxnix:" in architecture
    assert "Generated Nix templates" not in architecture
    assert "devenv tasks run autoconf:check" in architecture
    assert "devenv tasks run autoconf:generate" in architecture


def test_machine_map_exposes_autoconf_artifact_ownership() -> None:
    project_map = yaml.safe_load((REPO_ROOT / "luxnix.yml").read_text())
    ownership = project_map["artifact_ownership"]["autoconf"]

    assert set(ownership["canonical_sources"]) == {
        "ansible/inventory/hosts.ini",
        "ansible/inventory/home-hosts.yml",
        "ansible/inventory/group_vars",
        "ansible/inventory/host_vars",
        "autoconf/config.yml",
        "conf/nix-templates",
    }
    assert ownership["local_sensitive_inputs"] == ["ansible/cmdb/*.json"]
    assert set(ownership["generated_outputs"]) == {
        "autoconf/inventory.yml",
        "systems/x86_64-linux/<host>/default.nix",
        "homes/x86_64-linux/<user>@<host>/default.nix",
    }
    assert "derived output" in ownership["edit_rule"]
    assert ownership["validate_command"].endswith("autoconf:check")
    assert ownership["generate_command"].endswith("autoconf:generate")


def test_autoconf_guide_has_one_canonical_navigable_location() -> None:
    guide = DOCS_DIR / "autoconf.md"
    mkdocs = (REPO_ROOT / "mkdocs.yaml").read_text(encoding="utf-8")
    documentation_home = (DOCS_DIR / "index.md").read_text(encoding="utf-8")
    project_map = yaml.safe_load((REPO_ROOT / "luxnix.yml").read_text())

    assert guide.is_file()
    assert not (REPO_ROOT / "scripts/autoconf-pipeline.md").exists()
    assert "Autoconf and Local Inventory: autoconf.md" in mkdocs
    assert "./autoconf.md" in documentation_home
    assert project_map["support"]["autoconf"] == "docs/autoconf.md"
