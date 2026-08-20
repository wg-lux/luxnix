from __future__ import annotations

import subprocess
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client

from wg_lux_mcp.config import settings
from wg_lux_mcp.server import mcp
from wg_lux_mcp.tools.features import (
    AssessmentLedger,
    CurrentWork,
    CurrentWorkEvent,
    DeployedSubject,
    Evidence,
    FeatureIdentity,
    RequirementAssessmentEvent,
)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def assert_tool_error(result: Any, message: str) -> None:
    assert result.is_error is True
    assert result.content
    assert message in result.content[0].text


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "lx-annotate"
    repo.mkdir()
    git(repo, "init", "--initial-branch=main")
    git(repo, "config", "user.name", "Test Author")
    git(repo, "config", "user.email", "author@example.test")

    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    models = repo / "example" / "models.py"
    models.parent.mkdir()
    models.write_text(
        "class PatientExamination:\n"
        '    """Persisted patient examination."""\n'
        "    def save(self):\n"
        '        """Persist the selected knowledge base."""\n'
        '        return "knowledge base persistence"\n',
        encoding="utf-8",
    )
    related_test = repo / "tests" / "test_models.py"
    related_test.parent.mkdir()
    related_test.write_text(
        "from example.models import PatientExamination\n\n"
        "def test_patient_examination_save():\n"
        "    assert PatientExamination().save()\n",
        encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    migrations = repo / "demo_app" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "0001_initial.py").write_text("# migration\n", encoding="utf-8")
    feature_tracking = repo / "feature-tracking"
    feature_tracking.mkdir()
    (feature_tracking / "ExampleFeature.yml").write_text(
        """schema_version: '1.0'
id: example_feature
name: Example Feature
description: Demonstrate progressive feature retrieval.
owners:
  - test maintainers
production_critical: true
tracking:
  state: active
  history:
    - event: old-history-must-not-be-returned
invariants:
  - Existing behavior remains stable.
definition_of_done:
  - id: implemented
    category: functionality
    title: Feature is implemented
    acceptance:
      - Behavior is covered by a test.
    required: true
    verification:
      kind: command
      command: [pytest, -q]
    assessment:
      status: in_progress
      evidence:
        - kind: test
          reference: tests/test_example.py
      note: Focused implementation is underway.
      assessed_by: test-agent
      assessed_at: 2026-08-20
  - id: documented
    category: documentation
    title: Feature is documented
    acceptance:
      - Documentation exists.
    required: true
    verification:
      kind: manual
      instructions: Review the documentation.
    assessment:
      status: verified
      evidence:
        - kind: document
          reference: README.md
      assessed_by: reviewer
      assessed_at: '2026-08-20T10:00:00Z'
""",
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Initial commit")

    monkeypatch.setattr(settings, "repo_lx_annotate", repo)
    monkeypatch.setattr(settings, "repo_endoreg_db", tmp_path / "endoreg-db")
    monkeypatch.setattr(settings, "repo_lx_data_models", tmp_path / "lx-data-models")
    package = tmp_path / "nix-store" / "example-lx-annotate"
    feature_root = package / "share" / "lx-annotate" / "features"
    feature_root.mkdir(parents=True)
    (feature_root / "example_feature.yml").write_text(
        """schema_version: '1.0'
id: example_feature
name: Example Feature
description: Demonstrate deployed progressive feature retrieval.
owners: [test maintainers]
production_critical: true
invariants: [Existing behavior remains stable.]
definition_of_done:
  - id: implemented
    category: functionality
    title: Feature is implemented
    acceptance: [Behavior is covered by a test.]
    required: true
    verification:
      kind: command
      command: [pytest, -q]
  - id: documented
    category: documentation
    title: Feature is documented
    acceptance: [Documentation exists.]
    required: true
    verification:
      kind: manual
      instructions: Review the documentation.
""",
        encoding="utf-8",
    )
    registry = tmp_path / "providers.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "providers": {
                    "lx-annotate": {
                        "kind": "nix",
                        "feature_root": str(feature_root),
                        "package_store_path": str(package),
                        "drv_path": f"{package}.drv",
                        "revision": "test-revision",
                        "version": "1.0.0",
                        "system_generation": "test-generation",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    state_root = tmp_path / "feature-state"
    ledger = AssessmentLedger(state_root)
    identity = FeatureIdentity(provider="lx-annotate", id="example_feature")
    subject = DeployedSubject(
        provider="lx-annotate", feature_id="example_feature", nix_store_path=package
    )
    assessed_at = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    ledger.append(
        RequirementAssessmentEvent(
            feature=identity,
            requirement_id="implemented",
            status="in_progress",
            subject=subject,
            evidence=(Evidence(kind="test", reference="tests/test_example.py"),),
            note="Focused implementation is underway.",
            assessed_by="test-agent",
            assessed_at=assessed_at,
        )
    )
    ledger.append(
        RequirementAssessmentEvent(
            feature=identity,
            requirement_id="documented",
            status="verified",
            subject=subject,
            evidence=(Evidence(kind="document", reference="README.md"),),
            assessed_by="reviewer",
            assessed_at=assessed_at,
        )
    )
    ledger.append(
        CurrentWorkEvent(
            feature=identity,
            current_work=CurrentWork(
                objective="Finish the focused implementation.",
                scope=("implemented",),
                next=("Run pytest.",),
            ),
            subject=subject,
            assessed_by="test-agent",
            assessed_at=assessed_at,
        )
    )
    monkeypatch.setattr(settings, "feature_provider_registry", registry)
    monkeypatch.setattr(settings, "feature_state_root", state_root)
    return repo


def test_all_requested_capabilities(repository: Path) -> None:
    (repository / "untracked.txt").write_text("new\n", encoding="utf-8")

    async def run() -> None:
        async with Client(mcp) as client:
            repositories = await client.call_tool("list_repositories", {})
            assert repositories.structured_content == {
                "result": ["endoreg-db", "lx-annotate", "lx-data-models"]
            }

            status = await client.call_tool("get_repo_status", {"repo": "lx-annotate"})
            assert status.structured_content is not None
            assert status.structured_content["branch"] == "main"
            assert status.structured_content["clean"] is False
            assert status.structured_content["status"] == ["?? untracked.txt"]
            assert len(status.structured_content["head"]) == 40

            commits = await client.call_tool(
                "get_recent_commits", {"repo": "lx-annotate", "limit": 1}
            )
            assert commits.structured_content is not None
            assert commits.structured_content["result"][0]["author"] == "Test Author"
            assert commits.structured_content["result"][0]["subject"] == "Initial commit"

            text_file = await client.call_tool(
                "read_text_file",
                {"repo": "lx-annotate", "relative_path": "README.md", "max_chars": 3},
            )
            assert text_file.structured_content is not None
            assert text_file.structured_content["path"] == "README.md"
            assert text_file.structured_content["text"] == "hel"
            assert text_file.structured_content["truncated"] is True

            pyproject = await client.call_tool("get_pyproject", {"repo": "lx-annotate"})
            assert pyproject.structured_content is not None
            assert pyproject.structured_content["exists"] is True
            assert 'name = "example"' in pyproject.structured_content["text"]

            migrations = await client.call_tool(
                "inspect_django_migrations", {"repo": "lx-annotate", "app": "demo_app"}
            )
            assert migrations.structured_content == {
                "result": ["demo_app/migrations/0001_initial.py"]
            }

            code = await client.call_tool(
                "search_code",
                {"repo": "lx-annotate", "query": "knowledge base persistence"},
            )
            assert code.structured_content is not None
            assert code.structured_content["matches"][0]["sources"][0]["repo"] == "lx-annotate"
            assert len(code.structured_content["matches"][0]["sources"][0]["commit"]) == 40

            symbol = await client.call_tool(
                "find_symbol",
                {"repo": "lx-annotate", "symbol": "PatientExamination.save"},
            )
            assert symbol.structured_content is not None
            assert symbol.structured_content["matches"][0]["symbol"] == "PatientExamination.save"

            tests = await client.call_tool(
                "get_related_tests",
                {"repo": "lx-annotate", "path": "example/models.py"},
            )
            assert tests.structured_content is not None
            assert tests.structured_content["matches"][0]["sources"][0]["path"] == (
                "tests/test_models.py"
            )

            guidance = await client.call_tool("get_agent_guidance", {})
            assert guidance.structured_content is not None
            assert "source of truth" in guidance.structured_content["guidance"]

            project_context = await client.call_tool(
                "search_project_context", {"query": "progressive disclosure"}
            )
            assert project_context.structured_content is not None
            assert project_context.structured_content["matches"]

            current_work = await client.call_tool("get_current_work", {})
            assert current_work.structured_content is not None
            assert current_work.structured_content["goal"] == "deploy_wg_lux_mcp_context_service"
            assert current_work.structured_content["open"]
            assert (
                current_work.structured_content["blockers"]
                == current_work.structured_content["open"]
            )

            decision = await client.call_tool("get_decision", {"decision_id": "ADR-0002"})
            assert decision.structured_content is not None
            assert decision.structured_content["status"] == "accepted"

            references = await client.call_tool("list_references", {})
            assert references.structured_content is not None
            assert references.structured_content["result"][0]["id"] == "REF-0001"

            providers = await client.call_tool("list_feature_providers", {})
            assert providers.structured_content is not None
            assert providers.structured_content["result"][0]["provider"] == "lx-annotate"

            feature_list = await client.call_tool("list_features", {"provider": "lx-annotate"})
            assert feature_list.structured_content is not None
            assert feature_list.structured_content["result"][0]["feature"]["id"] == "example_feature"

            feature = await client.call_tool(
                "get_feature", {"provider": "lx-annotate", "feature_id": "example_feature"}
            )
            assert feature.structured_content is not None
            assert feature.structured_content["current_work"]["objective"] == (
                "Finish the focused implementation."
            )
            assert "assessment" not in feature.structured_content["specification"]

            feature_status = await client.call_tool(
                "get_feature_status",
                {"provider": "lx-annotate", "feature_id": "example_feature"},
            )
            assert feature_status.structured_content is not None
            assert feature_status.structured_content["state"] == "in_progress"
            assert feature_status.structured_content["verified_requirement_ids"] == ["documented"]

            feature_work = await client.call_tool(
                "get_current_feature_work",
                {"provider": "lx-annotate", "feature_id": "example_feature"},
            )
            assert feature_work.structured_content is not None
            assert (
                feature_work.structured_content["current_work"]["objective"]
                == "Finish the focused implementation."
            )

            requirement = await client.call_tool(
                "get_feature_requirement",
                {
                    "provider": "lx-annotate",
                    "feature_id": "example_feature",
                    "requirement_id": "implemented",
                },
            )
            assert requirement.structured_content is not None
            assert requirement.structured_content["assessment"]["status"] == "in_progress"
            assert "evidence" not in requirement.structured_content["assessment"]

            evidence = await client.call_tool(
                "get_feature_evidence",
                {
                    "provider": "lx-annotate",
                    "feature_id": "example_feature",
                    "requirement_id": "implemented",
                },
            )
            assert evidence.structured_content is not None
            assert evidence.structured_content["events"][0]["evidence"] == [
                {"kind": "test", "reference": "tests/test_example.py", "result": None, "note": None}
            ]

            subject = await client.call_tool(
                "get_deployed_feature_subject",
                {"provider": "lx-annotate", "feature_id": "example_feature"},
            )
            assert subject.structured_content is not None
            assert subject.structured_content["revision"] == "test-revision"

            capabilities = await client.call_tool("server_capabilities", {})
            assert capabilities.structured_content is not None
            assert capabilities.structured_content["mode"] == "read-only"
            assert capabilities.structured_content["git_writes"] is False
            assert capabilities.structured_content["retrieval"] == "progressive-disclosure"
            assert capabilities.structured_content["feature_tracking"]["writes"] is False

    anyio.run(run)


def test_rejects_unsafe_or_invalid_inputs(repository: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("external_secret_marker\n", encoding="utf-8")
    (repository / "external-link.md").symlink_to(outside)
    git(repository, "add", "external-link.md")
    git(repository, "commit", "-m", "Add external symlink fixture")

    async def run() -> None:
        async with Client(mcp) as client:
            unknown = await client.call_tool("get_repo_status", {"repo": "not-allowed"})
            assert_tool_error(unknown, "Unknown repository")

            escaped = await client.call_tool(
                "read_text_file",
                {"repo": "lx-annotate", "relative_path": "../outside.txt"},
            )
            assert_tool_error(escaped, "Path escapes repository root")

            bad_limit = await client.call_tool(
                "get_recent_commits", {"repo": "lx-annotate", "limit": 51}
            )
            assert_tool_error(bad_limit, "limit must be between 1 and 50")

            bad_app = await client.call_tool(
                "inspect_django_migrations", {"repo": "lx-annotate", "app": "1bad"}
            )
            assert_tool_error(bad_app, "simple Python identifier")

            bad_decision = await client.call_tool("get_decision", {"decision_id": "not-an-adr"})
            assert_tool_error(bad_decision, "form ADR-0001")

            symlink_search = await client.call_tool(
                "search_code",
                {"repo": "lx-annotate", "query": "external_secret_marker"},
            )
            assert symlink_search.structured_content is not None
            assert symlink_search.structured_content["matches"] == []

            unsupported_tracker = await client.call_tool(
                "list_features", {"provider": "lx-data-models"}
            )
            assert_tool_error(unsupported_tracker, "unknown deployed feature provider")

    anyio.run(run)
