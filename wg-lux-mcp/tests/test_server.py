from __future__ import annotations

import json
import subprocess
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
        provider="lx-annotate",
        feature_id="example_feature",
        nix_store_path=package,
        drv_path=Path(f"{package}.drv"),
        revision="test-revision",
        version="1.0.0",
        system_generation="test-generation",
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
            assert (
                feature_list.structured_content["result"][0]["feature"]["id"] == "example_feature"
            )

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


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.production",
        ".git/config",
        "private/settings.py",
        "secrets/config.yml",
        "credentials.json",
        "identity.key",
    ],
)
def test_repository_allowlist_does_not_allow_sensitive_files(repository: Path, name: str):
    from wg_lux_mcp.repo import RepositoryError
    from wg_lux_mcp.tools.repos import read_text_file
    from wg_lux_mcp.tools.search import search_code

    target = repository / name
    if not name.startswith(".git/"):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("private_audit_marker", encoding="utf-8")
        git(repository, "add", name)
        git(repository, "commit", "-m", "Sensitive path policy fixture")
    with pytest.raises(RepositoryError, match="Sensitive"):
        read_text_file("lx-annotate", name)
    assert search_code("lx-annotate", "private_audit_marker")["matches"] == []


def test_content_uses_commit_not_dirty_index_or_local_files(repository: Path):
    from wg_lux_mcp.tools.repos import get_pyproject, inspect_django_migrations, read_text_file
    from wg_lux_mcp.tools.search import find_symbol, get_related_tests, search_code

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    (repository / "README.md").write_text("dirty_only_marker\n")
    (repository / "example/models.py").write_text("def dirty_only_symbol(): pass\n")
    (repository / "pyproject.toml").write_text('[project]\nname="dirty_only_marker"\n')
    (repository / "tests/test_models.py").write_text("dirty_only_marker\n")
    (repository / "demo_app/migrations/0002_dirty.py").write_text("dirty_only_marker")
    (repository / "untracked.txt").write_text("private_audit_marker")
    git(repository, "add", "example/models.py")
    text = read_text_file("lx-annotate", "README.md")
    assert text["text"] == "hello\n" and text["commit"] == head
    assert len(text["blob"]) == 40
    with pytest.raises(FileNotFoundError, match="selected commit"):
        read_text_file("lx-annotate", "untracked.txt")
    assert "example" in get_pyproject("lx-annotate")["text"]
    assert inspect_django_migrations("lx-annotate", "demo_app") == [
        "demo_app/migrations/0001_initial.py"
    ]
    assert search_code("lx-annotate", "dirty_only_marker")["matches"] == []
    assert find_symbol("lx-annotate", "dirty_only_symbol")["matches"] == []
    assert find_symbol("lx-annotate", "PatientExamination")["matches"]
    related = get_related_tests("lx-annotate", "example/models.py")["matches"][0]
    assert related["sources"][0]["commit"] == head
    assert len(related["sources"][0]["blob"]) == 40


def test_committed_and_worktree_symlinks_cannot_read_private_content(
    repository: Path, tmp_path: Path
):
    from wg_lux_mcp.tools.repos import read_text_file

    outside = tmp_path / "private.txt"
    outside.write_text("outside_private_marker")
    (repository / "link.md").symlink_to(outside)
    git(repository, "add", "link.md")
    git(repository, "commit", "-m", "Symlink fixture")
    with pytest.raises(FileNotFoundError, match="public regular file"):
        read_text_file("lx-annotate", "link.md")
    (repository / "README.md").unlink()
    (repository / "README.md").symlink_to(outside)
    assert read_text_file("lx-annotate", "README.md")["text"] == "hello\n"


def test_enumeration_is_independent_of_response_limit_and_never_partial(
    repository: Path, monkeypatch
):
    from wg_lux_mcp import repo as boundary
    from wg_lux_mcp.tools.search import search_code

    for number in range(70):
        (repository / f"component_{number:03}_long_filename.py").write_text("ordinary = 1\n")
    (repository / "zzz_last_file.py").write_text("enumeration_end_marker = 1\n")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "Large filename list")
    monkeypatch.setattr(settings, "max_output_chars", 64)
    matches = search_code("lx-annotate", "enumeration_end_marker")["matches"]
    assert matches[0]["sources"][0]["path"] == "zzz_last_file.py"
    monkeypatch.setattr(boundary, "MAX_TREE_BYTES", 100)
    with pytest.raises(boundary.RepositoryError, match="no partial result"):
        search_code("lx-annotate", "enumeration_end_marker")


def test_git_response_overflow_is_explicit(repository: Path, monkeypatch):
    from wg_lux_mcp.repo import RepositoryError, run_readonly

    monkeypatch.setattr(settings, "max_output_chars", 10)
    with pytest.raises(RepositoryError, match="limit"):
        run_readonly(repository, ["git", "log", "--format=%H"])


def test_large_file_read_is_bounded_before_loading(repository: Path, monkeypatch):
    from wg_lux_mcp import repo as boundary
    from wg_lux_mcp.tools import repos, search

    data = "€" * 700_000
    (repository / "large.md").write_text(data, encoding="utf-8")
    git(repository, "add", "large.md")
    git(repository, "commit", "-m", "Large blob fixture")
    calls = []
    original = repos.read_blob

    def bounded(root, file, max_bytes, **kwargs):
        result = original(root, file, max_bytes, **kwargs)
        calls.append((max_bytes, len(result)))
        return result

    monkeypatch.setattr(repos, "read_blob", bounded)
    result = repos.read_text_file("lx-annotate", "large.md", max_chars=9)
    assert result["text"] == "€" * 9 and result["truncated"]
    assert calls == [(40, 40)]
    result = search.search_code("lx-annotate", "large_marker")
    assert result["skipped_large_files"] == 1
    # Read requests never need a complete tree or a complete file in memory.
    assert boundary.MAX_TREE_BYTES > 40


def test_unusual_filename_is_enumerated_without_splitting(repository: Path):
    from wg_lux_mcp.tools.repos import read_text_file
    from wg_lux_mcp.tools.search import search_code

    name = "line\nbreak.py"
    (repository / name).write_text("unusual_filename_marker = 1\n")
    git(repository, "add", name)
    git(repository, "commit", "-m", "NUL-delimited filename fixture")
    assert read_text_file("lx-annotate", name)["text"].startswith("unusual_filename_marker")
    assert (
        search_code("lx-annotate", "unusual_filename_marker")["matches"][0]["sources"][0]["path"]
        == name
    )
