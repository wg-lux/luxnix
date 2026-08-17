from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
from types import ModuleType
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "nix-quality.yml"


def _load_runner() -> ModuleType:
    path = REPO_ROOT / "scripts/nix-quality.py"
    spec = importlib.util.spec_from_file_location("nix_quality", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _policy() -> dict[str, Any]:
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))


def _passing_report(policy: dict[str, Any]) -> dict[str, Any]:
    checks = policy["checks"]
    return {
        "flake_source_visibility": {
            "command_ok": True,
            "exit_code": 0,
            "untracked_files": checks["flake_source_visibility"]["baseline"][
                "max_untracked_files"
            ],
        },
        "deadnix": {
            "command_ok": True,
            "exit_code": 0,
            "findings": checks["deadnix"]["baseline"]["max_findings"],
            "non_generated_findings": checks["deadnix"]["baseline"][
                "max_non_generated_findings"
            ],
        },
        "statix": {
            "command_ok": True,
            "exit_code": 1,
            "findings": checks["statix"]["baseline"]["max_findings"],
            "non_generated_findings": checks["statix"]["baseline"][
                "max_non_generated_findings"
            ],
        },
        "nixfmt": {
            "command_ok": True,
            "exit_code": 1,
            "unformatted_files": checks["nixfmt"]["baseline"]["max_unformatted_files"],
            "non_generated_unformatted_files": checks["nixfmt"]["baseline"][
                "max_non_generated_unformatted_files"
            ],
        },
        "flake_checker": {
            "command_ok": True,
            "exit_code": 0,
            "issues": checks["flake_checker"]["baseline"]["max_issues"],
        },
    }


def test_policy_has_ratcheted_nonnegative_baselines() -> None:
    policy = _policy()

    assert policy["schema_version"] == 1
    assert policy["formatter"]["command"] == "nixfmt"
    assert policy["policy"]["automatic_fixing"] == "disabled"
    for definition in policy["checks"].values():
        for value in definition.get("baseline", {}).values():
            assert isinstance(value, int) and value >= 0


def test_progress_history_is_monotonic_and_matches_current_baseline() -> None:
    policy = _policy()
    progress = policy["progress"]
    metric_to_baseline = {
        "flake_source_untracked_files": (
            "flake_source_visibility",
            "max_untracked_files",
        ),
        "deadnix_findings": ("deadnix", "max_findings"),
        "deadnix_non_generated_findings": (
            "deadnix",
            "max_non_generated_findings",
        ),
        "statix_findings": ("statix", "max_findings"),
        "statix_non_generated_findings": (
            "statix",
            "max_non_generated_findings",
        ),
        "nixfmt_unformatted_files": ("nixfmt", "max_unformatted_files"),
        "nixfmt_non_generated_unformatted_files": (
            "nixfmt",
            "max_non_generated_unformatted_files",
        ),
    }

    assert progress
    for metric, (check_name, baseline_name) in metric_to_baseline.items():
        values = [
            entry["metrics"][metric] for entry in progress if metric in entry["metrics"]
        ]
        assert values
        assert values == sorted(values, reverse=True)
        assert values[-1] == policy["checks"][check_name]["baseline"][baseline_name]


def test_generated_classification_matches_project_ownership() -> None:
    policy = _policy()
    runner = _load_runner()

    assert runner.is_generated("systems/x86_64-linux/gs-01/default.nix", policy)
    assert runner.is_generated(
        "systems/x86_64-linux/gs-01/boot-decryption-config.nix", policy
    )
    assert runner.is_generated("homes/x86_64-linux/admin@gs-01/default.nix", policy)
    assert not runner.is_generated("systems/x86_64-linux/lx-test/default.nix", policy)
    assert not runner.is_generated(
        "systems/x86_64-linux/c-01/boot-decryption-config.nix", policy
    )
    for host in ("gc-05", "gc-06", "gs-02"):
        assert not runner.is_generated(
            f"systems/x86_64-linux/{host}/boot-decryption-config.nix",
            policy,
        )
    assert not runner.is_generated(
        "modules/nixos/services/lx-annotate-local/default.nix", policy
    )


def test_every_generated_pattern_has_documented_canonical_sources() -> None:
    policy = _policy()
    scope = policy["scope"]
    documented_patterns = {
        definition["pattern"] for definition in scope["generated_sources"]
    }

    assert documented_patterns == set(scope["generated_patterns"])
    for definition in scope["generated_sources"]:
        assert definition["canonical_sources"]


def test_boot_decryption_outputs_have_a_safe_shared_renderer() -> None:
    policy = _policy()
    definition = next(
        source
        for source in policy["scope"]["generated_sources"]
        if source["pattern"] == "systems/x86_64-linux/*/boot-decryption-config.nix"
    )

    assert definition["safe_check"].startswith("bash -n ")
    assert "luxnix-render-boot-decryption-config" in definition["safe_render"]
    assert (
        "modules/nixos/luxnix/boot-decryption-stick/render-boot-decryption-config.sh"
        in definition["canonical_sources"]
    )


def test_generated_devenv_flake_is_outside_source_scope() -> None:
    policy = _policy()
    runner = _load_runner()
    files = {
        str(path.relative_to(REPO_ROOT)) for path in runner.nix_files(policy)
    }

    assert runner.is_excluded(".devenv.flake.nix", policy)
    assert ".devenv.flake.nix" not in files


def test_flake_source_visibility_covers_module_assets() -> None:
    policy = _policy()
    runner = _load_runner()

    assert "modules" in policy["scope"]["flake_source_roots"]
    report = runner.check_flake_source_visibility(policy)
    assert report == {
        "command_ok": True,
        "exit_code": 0,
        "untracked_files": 0,
        "files": [],
        "stderr": "",
    }


def test_baseline_is_a_ceiling_not_an_exact_snapshot() -> None:
    policy = _policy()
    runner = _load_runner()
    report = _passing_report(policy)

    assert runner.evaluate_baselines(report, policy, full=False) == []

    previous = report["deadnix"]["findings"]
    report["deadnix"]["findings"] += 1
    assert runner.evaluate_baselines(report, policy, full=False) == [
        f"deadnix.findings={previous + 1} exceeds baseline {previous}"
    ]


def test_quality_tools_are_owned_by_both_development_environments() -> None:
    required = {"deadnix", "statix", "nixfmt", "flake-checker"}
    devenv_packages = (REPO_ROOT / "devenv/packages.nix").read_text(encoding="utf-8")
    flake_shell = (REPO_ROOT / "shells/default/default.nix").read_text(encoding="utf-8")

    for package in required:
        assert package in devenv_packages
        assert package in flake_shell


def test_ci_runs_fast_checks_and_reserves_full_evaluation_for_ci() -> None:
    workflow = (REPO_ROOT / ".github/workflows/nix-quality.yml").read_text(
        encoding="utf-8"
    )

    assert "scripts/nix-quality.py --json" in workflow
    assert "scripts/nix-quality.py --full --json" in workflow
    assert "github.event_name == 'schedule'" in workflow
    assert "workflow_dispatch" in workflow


def test_flake_checker_is_ratcheted_in_fast_mode() -> None:
    policy = _policy()
    runner_source = (REPO_ROOT / "scripts/nix-quality.py").read_text(
        encoding="utf-8"
    )

    assert not policy["checks"]["flake_checker"].get("full_only", False)
    assert '"flake_checker": count_flake_checker(policy)' in runner_source
    assert 'help="also run nix flake check"' in runner_source


def test_precommit_fast_gate_includes_flake_lock() -> None:
    devenv_source = (REPO_ROOT / "devenv.nix").read_text(encoding="utf-8")
    hook = devenv_source.split("    nix-quality = {", 1)[1].split("\n    };", 1)[0]

    assert '^flake\\\\.lock$' in hook
    assert "|modules|" in hook
    assert "scripts/nix-quality.py" in hook


def test_flake_checker_report_exposes_outdated_inputs(monkeypatch) -> None:
    policy = _policy()
    runner = _load_runner()
    output = """The flake checker scanned flake.lock and discovered 2 issues
> The nixpkgs input is 201 days old
> The nixpkgs-unstable input is 40 days old
"""
    monkeypatch.setattr(
        runner,
        "run",
        lambda _command: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=output, stderr=""
        ),
    )

    report = runner.count_flake_checker(policy)

    assert report["issues"] == 2
    assert report["outdated_inputs"] == [
        {"input": "nixpkgs", "age_days": 201},
        {"input": "nixpkgs-unstable", "age_days": 40},
    ]


def test_generator_quality_gate_is_non_evaluating_and_always_uploads_junit() -> None:
    workflow = (REPO_ROOT / ".github/workflows/nix-quality.yml").read_text(
        encoding="utf-8"
    )
    generator_job = workflow.split("  generators:\n", 1)[1].split(
        "\n  full:\n", 1
    )[0]

    assert "name: Generated Nix renderer contracts" in generator_job
    assert "nix develop .#default --command uv run pytest -q" in generator_job
    assert "--junitxml=nix-quality-generators-junit.xml" in generator_job
    assert "if: always()" in generator_job
    assert "name: nix-quality-generators-junit" in generator_job
    assert "path: nix-quality-generators-junit.xml" in generator_job
    for test_target in (
        "tests/test_autoconf_rendering.py",
        "tests/test_ansible_autoconf_nixos_config.py",
        "tests/test_autoconf_cli.py",
        "tests/test_boot_decryption_renderer.py",
    ):
        assert test_target in generator_job
    for forbidden_command in (
        "nix eval",
        "nix flake check",
        "scripts/nix-quality.py",
        "--full",
    ):
        assert forbidden_command not in generator_job


def test_generator_quality_task_and_documentation_share_the_61_test_contract() -> None:
    task_definition = (REPO_ROOT / "devenv/tasks.nix").read_text(encoding="utf-8")
    project_map = yaml.safe_load((REPO_ROOT / "luxnix.yml").read_text(encoding="utf-8"))
    documentation = (REPO_ROOT / "docs/nix-quality.md").read_text(encoding="utf-8")

    task_start = task_definition.index('  "nix-quality:generators" = {')
    task_end = task_definition.index("\n  };", task_start)
    generator_task = task_definition[task_start:task_end]
    targets = project_map["quality"]["generator_tests"]

    workflows = {workflow["id"]: workflow for workflow in project_map["workflows"]}
    assert workflows["check-nix-quality-generators"] == {
        "id": "check-nix-quality-generators",
        "summary": (
            "Run 61 non-evaluating Autoconf and boot-decryption renderer contracts."
        ),
        "risk": "read-only",
        "documentation": "docs/nix-quality.md",
        "prerequisites": ["devenv"],
        "command": "devenv tasks run nix-quality:generators",
    }
    assert len(targets) == 4
    for target in targets:
        assert target in generator_task
    assert "devenv tasks run nix-quality:generators" in documentation
    assert "exactly 61 pytest cases in four files" in documentation
    assert (
        "`nix develop .#default` only supplies the pinned CI tool environment"
        in documentation
    )


def test_postgresql_service_settings_are_defined_once() -> None:
    module = (
        REPO_ROOT / "modules/nixos/services/postgres/default.nix"
    ).read_text(encoding="utf-8")

    assert module.count("settings = {") == 1


def test_vfio_uses_the_defined_libvirt_run_as_root_option() -> None:
    module = (
        REPO_ROOT / "modules/nixos/services/virtualisation/vfio/default.nix"
    ).read_text(encoding="utf-8")

    assert "cfg.qemu.runAsRoot" not in module
    assert "config.virtualisation.libvirtd.qemu.runAsRoot" in module


def test_custom_packages_combines_podman_flags_booleanly() -> None:
    module = (
        REPO_ROOT / "modules/nixos/roles/custom-packages/default.nix"
    ).read_text(encoding="utf-8")

    podman_expression = module.split("podmanEnabled =", 1)[1].split(";", 1)[0]
    assert podman_expression.count("||") == 2
