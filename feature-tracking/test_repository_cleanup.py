from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

REMOVED_LOCAL_ARTIFACTS = (
    "result.txt",
    "wg-lux-mcp.zip",
)

REMOVED_TRACKER_DOCUMENTS = (
    "feature-tracking/gs-02-local-redis-broker-proposal.yml",
    "feature-tracking/lx-annotate-hub-export-mtls-consumer-walkthrough.yml",
    "feature-tracking/vault-hub-simplification-plan.yml",
)

IGNORED_LOCAL_OUTPUTS = (
    "result/",
    ".devenv/",
    ".direnv/",
    ".ruff_cache/",
    ".pytest_cache/",
    "result.txt",
    "wg-lux-mcp.zip",
    "feature-tracking/.locks/example.json",
    "feature-tracking/.messages/example.json",
)

RETAINED_SOURCES = (
    "wg-lux-mcp/pyproject.toml",
    "feature-tracking/FrameCleanerIntegration.yml",
    "feature-tracking/ReportReaderIntegration.yml",
    "docs/operations/gs-02-local-redis-broker.md",
    "docs/vault-hub-machine-enrollment.md",
    "ansible/inventory/host_vars/gs-02.yml",
)


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *arguments),
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("relative_path", REMOVED_LOCAL_ARTIFACTS)
def test_generated_root_artifact_is_absent_and_ignored(relative_path: str) -> None:
    assert not (REPOSITORY_ROOT / relative_path).exists()
    ignored = _git("check-ignore", "--no-index", "--quiet", relative_path)
    assert ignored.returncode == 0, ignored.stderr


@pytest.mark.parametrize("relative_path", REMOVED_TRACKER_DOCUMENTS)
def test_migrated_tracker_document_is_absent(relative_path: str) -> None:
    assert not (REPOSITORY_ROOT / relative_path).exists()


@pytest.mark.parametrize("relative_path", IGNORED_LOCAL_OUTPUTS)
def test_local_output_is_ignored(relative_path: str) -> None:
    ignored = _git("check-ignore", "--no-index", "--quiet", relative_path)
    assert ignored.returncode == 0, ignored.stderr


@pytest.mark.parametrize("relative_path", RETAINED_SOURCES)
def test_cleanup_preserves_canonical_source(relative_path: str) -> None:
    assert (REPOSITORY_ROOT / relative_path).exists()


def test_removed_tracker_documents_have_no_retained_references() -> None:
    tracked = _git("ls-files", "-z")
    assert tracked.returncode == 0, tracked.stderr
    stale_references: list[str] = []

    for relative_path in tracked.stdout.split("\0"):
        candidate = REPOSITORY_ROOT / relative_path
        if not relative_path or not candidate.is_file():
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for removed_path in REMOVED_TRACKER_DOCUMENTS:
            if removed_path in content:
                stale_references.append(f"{relative_path}: {removed_path}")

    assert stale_references == []
