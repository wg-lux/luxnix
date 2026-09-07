from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
import yaml

from wg_lux_mcp.tools.features import (
    AssessmentLedger,
    CurrentWork,
    DeployedSubject,
    Evidence,
    FeatureIdentity,
    FeatureResolver,
    MalformedFeatureStateError,
    ProviderNotFoundError,
    RequirementAssessmentEvent,
    migrate_combined_tracker,
)


def write_specification(root: Path, feature_id: str = "semantic_feature") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{feature_id}.yml").write_text(
        f"""schema_version: '1.0'
id: {feature_id}
name: Semantic Feature
description: Resolve a feature independently of its deployed store path.
owners: [platform maintainers]
production_critical: true
invariants:
  - Semantic identity survives package replacement.
definition_of_done:
  - id: resolved
    category: functionality
    title: Semantic resolution succeeds
    acceptance: [The provider registry selects the exact package output.]
    required: true
    verification:
      kind: command
      command: [pytest, -q]
""",
        encoding="utf-8",
    )


def write_registry(
    path: Path,
    feature_root: Path,
    package: Path,
    *,
    kind: str = "nix",
) -> None:
    descriptor: dict[str, object] = {
        "kind": kind,
        "feature_root": str(feature_root),
        "package_store_path": str(package) if kind == "nix" else None,
        "drv_path": f"{package}.drv" if kind == "nix" else None,
        "revision": "abc123",
        "version": "1.0.0",
        "system_generation": "generation-42",
    }
    if kind == "development":
        descriptor.pop("package_store_path")
    path.write_text(
        json.dumps({"schema_version": "1.0", "providers": {"example": descriptor}}),
        encoding="utf-8",
    )


def test_semantic_identity_survives_environment_replacement(tmp_path: Path) -> None:
    state = tmp_path / "state"
    registry = tmp_path / "providers.json"
    package_a = tmp_path / "nix-store" / "aaa-example-1"
    root_a = package_a / "share" / "example" / "features"
    write_specification(root_a)
    write_registry(registry, root_a, package_a)

    resolver_a = FeatureResolver(registry, state)
    assert resolver_a.get_feature("example", "semantic_feature")["feature"] == {
        "provider": "example",
        "id": "semantic_feature",
    }
    assert resolver_a.get_deployed_feature_subject("example", "semantic_feature")[
        "nix_store_path"
    ] == str(package_a)

    package_b = tmp_path / "nix-store" / "bbb-example-2"
    root_b = package_b / "share" / "example" / "features"
    write_specification(root_b)
    write_registry(registry, root_b, package_b)
    resolver_b = FeatureResolver(registry, state)
    assert resolver_b.get_feature("example", "semantic_feature")["feature"] == {
        "provider": "example",
        "id": "semantic_feature",
    }
    assert resolver_b.get_deployed_feature_subject("example", "semantic_feature")[
        "nix_store_path"
    ] == str(package_b)


def test_provider_feature_and_schema_fail_closed(tmp_path: Path) -> None:
    package = tmp_path / "package"
    root = package / "share" / "example" / "features"
    write_specification(root)
    registry = tmp_path / "providers.json"
    write_registry(registry, root, package)
    resolver = FeatureResolver(registry, tmp_path / "state")

    with pytest.raises(ProviderNotFoundError, match="unknown deployed feature provider"):
        resolver.list_features("missing")
    with pytest.raises(Exception, match="unknown feature identity"):
        resolver.get_feature("example", "missing")

    (root / "broken.yml").write_text("id: broken\nassessment: mutable\n", encoding="utf-8")
    with pytest.raises(MalformedFeatureStateError, match="malformed feature specification"):
        resolver.list_features("example")


def test_development_provider_never_masquerades_as_deployed(tmp_path: Path) -> None:
    root = tmp_path / "checkout" / "features"
    write_specification(root)
    registry = tmp_path / "providers.json"
    write_registry(registry, root, tmp_path / "checkout", kind="development")
    resolver = FeatureResolver(registry, tmp_path / "state")
    assert resolver.list_feature_providers()[0]["kind"] == "development"
    with pytest.raises(ProviderNotFoundError, match="development-only"):
        resolver.list_features("example")


def test_projection_reconstructs_history_and_status_does_not_scan_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    root = package / "share" / "example" / "features"
    write_specification(root)
    registry = tmp_path / "providers.json"
    write_registry(registry, root, package)
    resolver = FeatureResolver(registry, tmp_path / "state")
    identity = FeatureIdentity(provider="example", id="semantic_feature")
    subject = DeployedSubject(
        provider="example", feature_id="semantic_feature", nix_store_path=package
    )
    event = RequirementAssessmentEvent(
        event_id="stable-event",
        feature=identity,
        requirement_id="resolved",
        status="verified",
        subject=subject,
        evidence=(Evidence(kind="test", reference="tests/test_semantic.py", result="passed"),),
        assessed_by="tester",
        assessed_at=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    )
    resolver.ledger.append(event)
    projection = resolver.ledger.rebuild_projection("example", "semantic_feature")
    assert projection.requirements["resolved"].status == "verified"

    monkeypatch.setattr(
        resolver.ledger,
        "_events",
        lambda *_args: (_ for _ in ()).throw(AssertionError("status scanned event history")),
    )
    status = resolver.get_feature_status("example", "semantic_feature")
    assert status["verified_requirement_ids"] == ["resolved"]
    assert "evidence" not in json.dumps(status)

    monkeypatch.undo()
    evidence = resolver.get_feature_evidence("example", "semantic_feature", "resolved")
    events = cast(list[dict[str, object]], evidence["events"])
    evidence_items = cast(list[dict[str, object]], events[0]["evidence"])
    assert evidence_items[0]["result"] == "passed"


def test_migration_separates_specification_assessment_and_current_work(tmp_path: Path) -> None:
    source = tmp_path / "Combined.yml"
    source.write_text(
        """schema_version: '1.0'
id: migrated_feature
name: Migrated Feature
description: Preserve all legacy readiness information.
owners: [maintainers]
production_critical: true
tracking:
  state: active
  history: []
invariants: [Never lose historical evidence.]
current_work:
  objective: Finish migration.
  scope: [legacy tracker]
  next: [Rebuild the projection.]
definition_of_done:
  - id: preserved
    category: testing
    title: Evidence is preserved
    acceptance: [All assessment fields survive migration.]
    required: true
    verification:
      kind: command
      command: [pytest, -q]
    assessment:
      status: verified
      evidence:
        - kind: test
          reference: tests/test_migration.py
          result: passed
      note: Legacy note.
      assessed_by: legacy-agent
      assessed_at: '2026-08-20T10:00:00Z'
""",
        encoding="utf-8",
    )
    state = tmp_path / "state"
    ledger = AssessmentLedger(state)
    subject = DeployedSubject(
        provider="example",
        feature_id="migrated_feature",
        nix_store_path=Path("/nix/store/example"),
        drv_path=Path("/nix/store/example.drv"),
        revision="abc123",
    )
    specification_path, events = migrate_combined_tracker(
        provider="example",
        source_path=source,
        specification_root=tmp_path / "specifications",
        ledger=ledger,
        subject=subject,
    )
    specification = yaml.safe_load(specification_path.read_text(encoding="utf-8"))
    assert "tracking" not in specification
    assert "current_work" not in specification
    assert "assessment" not in specification["definition_of_done"][0]
    assert len(events) == 2
    projection = ledger.load_projection("example", "migrated_feature")
    assert projection.requirements["preserved"].note == "Legacy note."
    assert projection.current_work == CurrentWork(
        objective="Finish migration.",
        scope=("legacy tracker",),
        next=("Rebuild the projection.",),
    )
    evidence_rows, total = ledger.evidence("example", "migrated_feature", "preserved", 0, 20)
    assert total == 1
    assert evidence_rows[0]["assessed_by"] == "legacy-agent"
    evidence_items = cast(list[dict[str, object]], evidence_rows[0]["evidence"])
    assert evidence_items[0]["reference"] == "tests/test_migration.py"
