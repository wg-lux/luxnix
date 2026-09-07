from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from lx_administration.utils.file_operations import (
    advisory_file_lock,
    atomic_create_file,
    atomic_write_file,
    safe_unlink_file,
)
from tracker import (
    TRACKING_DIR,
    Assessment,
    AssessmentStatus,
    Evidence,
    EvidenceKind,
    ExecutionMode,
    ExternalCodexExecBackend,
    FeatureDefinition,
    FeatureTrackingState,
    FindingConfidence,
    NativeSubagentBackend,
    OrchestrationContract,
    ReadinessStatus,
    TaskTopology,
    TrackerError,
    WorkerFinding,
    WorkerResult,
    WorkUnit,
    WorkUnitStatus,
    actively_tracked_features,
    checkpoint_orchestration,
    derive_readiness,
    find_feature_references,
    guard_commit_message,
    load_feature_file,
    load_registry,
    load_registry_from_git_index,
    main,
    mark_feature_done,
    reopen_feature,
    save_feature,
    update_assessment,
)

ASSESSMENT_TIME = datetime.fromisoformat("2026-07-17T10:00:00+00:00")


def _fixture_feature(
    *,
    feature_id: str = "fixture_feature",
    name: str = "Fixture Feature",
    primary_criterion_id: str = "fixture_scope",
    command_verification: bool = False,
) -> FeatureDefinition:
    payload = yaml.safe_load(
        (TRACKING_DIR / "schema.example.yml").read_text(encoding="utf-8"),
    )
    payload.update({"id": feature_id, "name": name, "source_documents": []})
    base_criterion = payload["definition_of_done"][0]
    criteria = []
    for index, category in enumerate(
        (
            "requirements",
            "functionality",
            "testing",
            "security",
            "operations",
            "documentation",
        ),
    ):
        criterion = dict(base_criterion)
        criterion["id"] = primary_criterion_id if index == 0 else f"fixture_{category}"
        criterion["category"] = category
        if index == 0 and command_verification:
            criterion["verification"] = {
                "kind": "command",
                "command": ["python3", "-c", "raise SystemExit(0)"],
                "timeout_seconds": 30,
            }
        criteria.append(criterion)
    payload["definition_of_done"] = criteria
    return FeatureDefinition.model_validate(payload)


def _verified_feature(feature: FeatureDefinition) -> FeatureDefinition:
    verified = Assessment(
        status=AssessmentStatus.VERIFIED,
        evidence=(Evidence(kind=EvidenceKind.REVIEW, reference="review-42"),),
        assessed_by="reviewer@example.org",
        assessed_at=ASSESSMENT_TIME,
    )
    criteria = tuple(
        criterion.model_copy(update={"assessment": verified})
        for criterion in feature.definition_of_done
    )
    return FeatureDefinition(
        schema_version=feature.schema_version,
        id=feature.id,
        name=feature.name,
        description=feature.description,
        owners=feature.owners,
        production_critical=feature.production_critical,
        tracking=feature.tracking,
        source_documents=feature.source_documents,
        definition_of_done=criteria,
    )


def _unassessed_feature(feature: FeatureDefinition) -> FeatureDefinition:
    criteria = tuple(
        criterion.model_copy(update={"assessment": Assessment()})
        for criterion in feature.definition_of_done
    )
    return feature.model_copy(
        update={
            "source_documents": (),
            "definition_of_done": criteria,
        },
    )


def _run_git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def test_project_local_atomic_file_operations_preserve_contract(tmp_path: Path) -> None:
    destination = tmp_path / "private/state.json"
    created = atomic_create_file(
        destination=destination,
        content=(b'{"state":"created"}\n',),
        required_bytes=20,
        file_mode=0o600,
        dir_mode=0o700,
    )

    assert created.read_bytes() == b'{"state":"created"}\n'
    assert created.stat().st_mode & 0o777 == 0o600
    assert created.parent.stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError):
        atomic_create_file(destination=created, content=(b"replacement",))

    atomic_write_file(
        destination=created,
        content=(b'{"state":"updated"}\n',),
        file_mode=0o600,
    )
    assert created.read_bytes() == b'{"state":"updated"}\n'
    assert not tuple(created.parent.glob(f".{created.name}.tmp.*"))

    safe_unlink_file(created)
    safe_unlink_file(created)
    assert not created.exists()


def test_project_local_advisory_lock_rejects_concurrent_owner(tmp_path: Path) -> None:
    lock_path = tmp_path / "tracker.lock"

    with advisory_file_lock(lock_path=lock_path):
        with pytest.raises(TimeoutError):
            with advisory_file_lock(lock_path=lock_path, timeout_seconds=0):
                pytest.fail("a second lock owner must not enter")

    with advisory_file_lock(lock_path=lock_path, timeout_seconds=0):
        assert lock_path.read_text(encoding="ascii").startswith("pid=")


def test_repository_registry_is_valid_and_tracks_current_assessments() -> None:
    _, features = load_registry(TRACKING_DIR)
    feature_paths = tuple(
        path
        for path in TRACKING_DIR.glob("*.yml")
        if path.name not in {"policy.yml", "schema.example.yml"}
    )

    assert len(features) == len(feature_paths)
    assert len({feature.id for feature in features}) == len(features)
    assert features
    for feature in features:
        readiness = derive_readiness(feature)
        assert 0 <= readiness.verified_required <= readiness.required_total
        assert 0 <= readiness.score_percent <= 100


def test_verified_status_requires_evidence_and_assessor() -> None:
    with pytest.raises(ValueError, match="require evidence"):
        Assessment(
            status=AssessmentStatus.VERIFIED,
            assessed_by="reviewer@example.org",
            assessed_at=ASSESSMENT_TIME,
        )


def test_all_required_criteria_must_be_verified_for_production() -> None:
    ready = _verified_feature(_fixture_feature())

    result = derive_readiness(ready)

    assert result.status is ReadinessStatus.PRODUCTION_READY
    assert result.score_percent == 100


def test_update_and_atomic_save_round_trip(tmp_path: Path) -> None:
    feature = _fixture_feature(primary_criterion_id="fixture_scope")
    updated = update_assessment(
        feature,
        criterion_id="fixture_scope",
        status=AssessmentStatus.IN_PROGRESS,
        assessed_by="reviewer@example.org",
        note="Review läuft.",
    )

    destination = save_feature(updated, tmp_path)
    loaded = load_feature_file(destination)

    criterion = next(
        item for item in loaded.definition_of_done if item.id == "fixture_scope"
    )
    assert criterion.assessment.status is AssessmentStatus.IN_PROGRESS
    assert criterion.assessment.assessed_by == "reviewer@example.org"
    assert not tuple(tmp_path.glob("*.tmp.*"))


def test_save_feature_preserves_existing_filename_case(tmp_path: Path) -> None:
    feature = _fixture_feature()
    existing = tmp_path / "FixtureFeature.yml"
    existing.write_text("placeholder: true\n", encoding="utf-8")

    destination = save_feature(feature, tmp_path)

    assert destination == existing
    assert not (tmp_path / "fixture_feature.yml").exists()
    assert load_feature_file(existing).id == "fixture_feature"


def test_file_name_must_match_feature_id(tmp_path: Path) -> None:
    payload = _fixture_feature().model_dump(mode="json", exclude_none=True)
    path = tmp_path / "wrong_name.yml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(TrackerError, match="Dateiname und Feature-ID"):
        load_feature_file(path)


def test_check_returns_failure_until_definition_of_done_is_verified(
    tmp_path: Path,
) -> None:
    policy, _ = load_registry(TRACKING_DIR)
    feature = _fixture_feature()
    tracking_dir = tmp_path / "feature-tracking"
    tracking_dir.mkdir()
    (tracking_dir / "policy.yml").write_text(
        yaml.safe_dump(
            policy.model_copy(update={"migrated_markdown_trackers": ()}).model_dump(
                mode="json",
            ),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (tracking_dir / "FixtureFeature.yml").write_text(
        yaml.safe_dump(feature.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )

    assert main(["--directory", str(tracking_dir), "check", "fixture_feature"]) == 1


def test_verify_update_requires_assessor_before_command_runs(tmp_path: Path) -> None:
    policy, _ = load_registry(TRACKING_DIR)
    tracking_dir = tmp_path / "feature-tracking"
    tracking_dir.mkdir()
    (tracking_dir / "policy.yml").write_text(
        yaml.safe_dump(policy.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    feature = _fixture_feature(
        primary_criterion_id="terminal_command",
        command_verification=True,
    )
    (tracking_dir / "FixtureFeature.yml").write_text(
        yaml.safe_dump(feature.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(TrackerError, match="erfordert --assessed-by"):
        main(
            [
                "--directory",
                str(tracking_dir),
                "verify",
                "fixture_feature",
                "terminal_command",
                "--update",
            ],
        )


def test_feature_references_match_ids_names_and_separator_variants() -> None:
    features = (
        _fixture_feature(feature_id="alpha_test_feature", name="Alpha Test Feature"),
        _fixture_feature(feature_id="beta_test_feature", name="Beta Test Feature"),
    )

    matched = find_feature_references(
        "feat(alpha-test-feature): align Beta Test Feature",
        features,
    )

    assert {feature.id for feature in matched} == {
        "alpha_test_feature",
        "beta_test_feature",
    }
    assert find_feature_references("documentation cleanup", features) == ()


def test_commit_guard_uses_staged_readiness_not_unstaged_yaml(
    tmp_path: Path,
) -> None:
    feature = _fixture_feature()
    policy, _ = load_registry(TRACKING_DIR)
    staged_policy = policy.model_copy(update={"migrated_markdown_trackers": ()})
    tracking_dir = tmp_path / "feature-tracking"
    tracking_dir.mkdir()
    (tracking_dir / "policy.yml").write_text(
        yaml.safe_dump(staged_policy.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    feature_path = tracking_dir / "FixtureFeature.yml"
    feature_path.write_text(
        yaml.safe_dump(feature.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    _run_git(tmp_path, "init", "--quiet")
    _run_git(tmp_path, "add", "feature-tracking")

    message_path = tmp_path / "COMMIT_EDITMSG"
    message_path.write_text(
        "feat(fixture-feature): production release\n",
        encoding="utf-8",
    )
    assert guard_commit_message(message_path, repository_root=tmp_path) == 1

    feature_path.write_text(
        yaml.safe_dump(
            _verified_feature(feature).model_dump(mode="json"),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _, indexed_features = load_registry_from_git_index(tmp_path)
    assert derive_readiness(indexed_features[0]).status is ReadinessStatus.EVALUATED
    assert guard_commit_message(message_path, repository_root=tmp_path) == 1

    _run_git(tmp_path, "add", feature_path.relative_to(tmp_path).as_posix())
    assert guard_commit_message(message_path, repository_root=tmp_path) == 0


def test_default_overview_lists_all_active_valid_features(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, features = load_registry(TRACKING_DIR)
    active_count = len(actively_tracked_features(features))
    done_count = sum(
        feature.tracking.state is FeatureTrackingState.DONE for feature in features
    )

    assert main([]) == 0

    output = capsys.readouterr().out
    for feature in actively_tracked_features(features):
        assert feature.name in output
    assert f"Aktiv getrackt: {active_count}; Done: {done_count}" in output


def test_done_requires_complete_dod_and_excludes_feature_from_tracking() -> None:
    feature = _fixture_feature(primary_criterion_id="defined_structure")

    with pytest.raises(TrackerError, match="kann nicht done gesetzt werden"):
        mark_feature_done(
            feature,
            changed_by="reviewer@example.org",
            note="Release freigegeben.",
        )

    completed = mark_feature_done(
        _verified_feature(feature),
        changed_by="reviewer@example.org",
        note="Release freigegeben.",
    )

    assert completed.tracking.state is FeatureTrackingState.DONE
    assert actively_tracked_features((completed,)) == ()
    assert find_feature_references("feat(fixture-feature): release", (completed,)) == ()

    reopened = reopen_feature(
        completed,
        criterion_id="defined_structure",
        changed_by="reviewer@example.org",
        note="Neue Anforderungen.",
    )
    assert reopened.tracking.state is FeatureTrackingState.ACTIVE
    assert actively_tracked_features((reopened,)) == (reopened,)
    assert len(reopened.tracking.history) == 2
    assert derive_readiness(reopened).status is ReadinessStatus.IN_PROGRESS


def _work_unit(unit_id: str, *, depends_on: tuple[str, ...] = ()) -> WorkUnit:
    return WorkUnit(
        id=unit_id,
        responsibility=f"Review {unit_id}",
        criterion_id="terminal_workflow",
        depends_on=depends_on,
        max_turns=1,
        token_budget=1_000,
    )


def test_orchestration_contract_matches_execution_mode_to_topology() -> None:
    with pytest.raises(ValueError, match="sequential topology requires single_agent"):
        OrchestrationContract(
            run_id="sequential-review",
            feature_id="standard",
            orchestrator="codex/root",
            topology=TaskTopology.SEQUENTIAL_INTERDEPENDENT,
            execution_mode=ExecutionMode.CENTRALIZED_MULTI_AGENT,
            max_workers=2,
            total_token_budget=2_000,
            work_units=(_work_unit("first"), _work_unit("second")),
        )

    parallel = OrchestrationContract(
        run_id="parallel-review",
        feature_id="standard",
        orchestrator="codex/root",
        topology=TaskTopology.INDEPENDENT_PARALLEL,
        execution_mode=ExecutionMode.CENTRALIZED_MULTI_AGENT,
        agent_backend=NativeSubagentBackend(agent_profile="explorer"),
        max_workers=2,
        total_token_budget=2_000,
        work_units=(_work_unit("first"), _work_unit("second")),
    )

    assert parallel.max_workers == 2


def test_orchestration_contract_enforces_dependency_and_budget_guardrails() -> None:
    with pytest.raises(ValueError, match="at least two non-blocking root"):
        OrchestrationContract(
            run_id="false-parallelism",
            feature_id="standard",
            orchestrator="codex/root",
            topology=TaskTopology.INDEPENDENT_PARALLEL,
            execution_mode=ExecutionMode.CENTRALIZED_MULTI_AGENT,
            agent_backend=NativeSubagentBackend(),
            max_workers=2,
            total_token_budget=2_000,
            work_units=(
                _work_unit("first"),
                _work_unit("second", depends_on=("first",)),
            ),
        )

    with pytest.raises(ValueError, match="exceeding the 1000 token budget"):
        OrchestrationContract(
            run_id="over-budget",
            feature_id="standard",
            orchestrator="codex/root",
            topology=TaskTopology.SEQUENTIAL_INTERDEPENDENT,
            execution_mode=ExecutionMode.SINGLE_AGENT,
            max_workers=1,
            total_token_budget=1_000,
            work_units=(_work_unit("first"), _work_unit("second")),
        )


def test_worker_result_schema_and_checkpoints_are_strict_and_idempotent() -> None:
    contract = OrchestrationContract(
        run_id="checkpoint-review",
        feature_id="standard",
        orchestrator="codex/root",
        topology=TaskTopology.SEQUENTIAL_INTERDEPENDENT,
        execution_mode=ExecutionMode.SINGLE_AGENT,
        max_workers=1,
        total_token_budget=1_000,
        work_units=(_work_unit("review"),),
    )
    in_progress = checkpoint_orchestration(
        contract,
        work_unit_id="review",
        status=WorkUnitStatus.IN_PROGRESS,
    )
    assert (
        checkpoint_orchestration(
            in_progress,
            work_unit_id="review",
            status=WorkUnitStatus.IN_PROGRESS,
        )
        is in_progress
    )

    result = WorkerResult(
        task_status="complete",
        findings=(
            WorkerFinding(
                claim="The focused contract passes.",
                source="feature-tracking/test_tracker.py",
                confidence=FindingConfidence.HIGH,
            ),
        ),
    )
    complete = checkpoint_orchestration(
        in_progress,
        work_unit_id="review",
        status=WorkUnitStatus.COMPLETE,
        result=result,
    )
    assert complete.work_units[0].result == result
    with pytest.raises(TrackerError, match="complete -> in_progress"):
        checkpoint_orchestration(
            complete,
            work_unit_id="review",
            status=WorkUnitStatus.IN_PROGRESS,
        )


def test_orchestration_contract_distinguishes_native_and_external_workers() -> None:
    external = ExternalCodexExecBackend(sandbox_mode="read-only")
    contract = OrchestrationContract(
        run_id="external-review",
        feature_id="standard",
        orchestrator="codex/root",
        topology=TaskTopology.INDEPENDENT_PARALLEL,
        execution_mode=ExecutionMode.CENTRALIZED_MULTI_AGENT,
        agent_backend=external,
        max_workers=2,
        total_token_budget=2_000,
        work_units=(_work_unit("first"), _work_unit("second")),
    )

    assert contract.agent_backend == external
    assert external.command_prefix == (
        "codex",
        "exec",
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
    )

    with pytest.raises(ValueError, match="requires an explicit agent backend"):
        OrchestrationContract(
            run_id="missing-backend",
            feature_id="standard",
            orchestrator="codex/root",
            topology=TaskTopology.INDEPENDENT_PARALLEL,
            execution_mode=ExecutionMode.CENTRALIZED_MULTI_AGENT,
            max_workers=2,
            total_token_budget=2_000,
            work_units=(_work_unit("first"), _work_unit("second")),
        )

    with pytest.raises(ValueError, match="cannot define an agent backend"):
        OrchestrationContract(
            run_id="single-with-backend",
            feature_id="standard",
            orchestrator="codex/root",
            topology=TaskTopology.SEQUENTIAL_INTERDEPENDENT,
            execution_mode=ExecutionMode.SINGLE_AGENT,
            agent_backend=NativeSubagentBackend(),
            max_workers=1,
            total_token_budget=1_000,
            work_units=(_work_unit("review"),),
        )
