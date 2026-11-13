"""Migration stages are durable, ordered and idempotent; never proof of disk state."""

import json

import pytest

from lx_administration.storage import migration_lifecycle as life

PLAN = "a" * 64
ORDER = [
    life.Stage.MIGRATING,
    life.Stage.VERIFYING,
    life.Stage.ACTIVATING,
    life.Stage.COMPLETED,
]


def walk(state, stop=None):
    for stage in ORDER:
        record = life.advance(state, PLAN, stage)
        if stage == stop:
            break
    return record


def test_stages_advance_in_order_and_persist(tmp_path):
    assert walk(tmp_path)["stage"] == "completed"
    assert life.load(tmp_path, PLAN)["stage"] == "completed"


def test_repeating_a_stage_changes_nothing(tmp_path):
    walk(tmp_path, life.Stage.VERIFYING)
    before = (tmp_path / life.FILE).read_text()
    life.advance(tmp_path, PLAN, life.Stage.VERIFYING)
    assert (tmp_path / life.FILE).read_text() == before


@pytest.mark.parametrize(
    "stop,target",
    [
        (None, life.Stage.ACTIVATING),
        (life.Stage.MIGRATING, life.Stage.COMPLETED),
        (life.Stage.COMPLETED, life.Stage.MIGRATING),
    ],
)
def test_invalid_transitions_are_rejected(tmp_path, stop, target):
    if stop:
        walk(tmp_path, stop)
    with pytest.raises(life.LifecycleError):
        life.advance(tmp_path, PLAN, target)


def test_interrupted_stage_resumes_only_where_it_stopped(tmp_path):
    walk(tmp_path, life.Stage.MIGRATING)
    life.fail(tmp_path, PLAN, "power loss")
    with pytest.raises(life.LifecycleError):
        life.advance(tmp_path, PLAN, life.Stage.ACTIVATING)
    assert life.advance(tmp_path, PLAN, life.Stage.MIGRATING)["failed_from"] is None


def test_repeated_failure_is_idempotent(tmp_path):
    walk(tmp_path, life.Stage.MIGRATING)
    first = life.fail(tmp_path, PLAN, "power loss")
    assert life.fail(tmp_path, PLAN, "again") == first


def test_completed_migration_cannot_fail(tmp_path):
    walk(tmp_path)
    with pytest.raises(life.LifecycleError):
        life.fail(tmp_path, PLAN, "late")


def test_record_from_another_plan_is_rejected(tmp_path):
    walk(tmp_path, life.Stage.MIGRATING)
    with pytest.raises(life.LifecycleError):
        life.load(tmp_path, "b" * 64)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 999},
        {"stage": "failed", "failed_from": "completed"},
        {"stage": "failed", "failed_from": None},
        {"stage": "migrating", "failed_from": "migrating"},
    ],
)
def test_tampered_records_are_rejected(tmp_path, change):
    walk(tmp_path, life.Stage.MIGRATING)
    path = tmp_path / life.FILE
    path.write_text(json.dumps(json.loads(path.read_text()) | change))
    with pytest.raises(life.LifecycleError):
        life.load(tmp_path, PLAN)


@pytest.mark.parametrize(
    "phase,install,accepted,stage,failed_from",
    [
        (None, "pending", False, "preparing", None),
        ("planned", "pending", False, "preparing", None),
        ("running", "pending", False, "failed", "migrating"),
        ("interrupted", "pending", False, "failed", "migrating"),
        ("complete", "pending", False, "verifying", None),
        ("complete", "running", False, "failed", "activating"),
        ("complete", "interrupted", False, "failed", "activating"),
        ("complete", "complete", False, "activating", None),
        ("complete", "complete", True, "completed", None),
    ],
)
def test_existing_migrations_are_placed_by_their_journals(
    phase, install, accepted, stage, failed_from
):
    derived = life.derive(phase, install, accepted)
    assert (derived["stage"], derived["failed_from"]) == (stage, failed_from)
