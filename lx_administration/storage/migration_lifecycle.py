"""Durable migration stage record. A stage is history, never proof of disk state."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
import json
import time

from lx_administration.storage.cutover import atomic_json

FILE = "lifecycle.json"


class Stage(StrEnum):
    PREPARING = "preparing"
    MIGRATING = "migrating"
    VERIFYING = "verifying"
    ACTIVATING = "activating"
    COMPLETED = "completed"
    FAILED = "failed"


TRANSITIONS = {
    Stage.PREPARING: {Stage.MIGRATING, Stage.FAILED},
    Stage.MIGRATING: {Stage.VERIFYING, Stage.FAILED},
    Stage.VERIFYING: {Stage.ACTIVATING, Stage.FAILED},
    Stage.ACTIVATING: {Stage.COMPLETED, Stage.FAILED},
    Stage.COMPLETED: set(),
    # A failed stage may only resume where it stopped; see advance().
    Stage.FAILED: set(),
}


RESUMABLE = {Stage.PREPARING, Stage.MIGRATING, Stage.VERIFYING, Stage.ACTIVATING}


class LifecycleError(ValueError):
    """An operation was requested from a stage that does not allow it."""


def derive(journal_phase: str | None, install_status: str, accepted: bool) -> dict:
    """Place a migration begun before this record existed; progress is positional."""
    if accepted and install_status == "complete":
        return {"stage": Stage.COMPLETED, "failed_from": None}
    if install_status == "complete":
        return {"stage": Stage.ACTIVATING, "failed_from": None}
    if install_status in {"running", "interrupted"}:
        return {"stage": Stage.FAILED, "failed_from": Stage.ACTIVATING}
    if journal_phase == "complete":
        return {"stage": Stage.VERIFYING, "failed_from": None}
    if journal_phase in {"running", "interrupted"}:
        return {"stage": Stage.FAILED, "failed_from": Stage.MIGRATING}
    return {"stage": Stage.PREPARING, "failed_from": None}


def load(state: Path, plan_id: str, initial: dict | None = None) -> dict:
    path = state / FILE
    if not path.exists():
        start = initial or {"stage": Stage.PREPARING, "failed_from": None}
        return {
            "schema_version": 1,
            "plan_id": plan_id,
            "stage": str(start["stage"]),
            "failed_from": start["failed_from"] and str(start["failed_from"]),
            "evidence": {},
            "history": [],
        }
    record = json.loads(path.read_text())
    if (
        record.get("schema_version") != 1
        or record.get("plan_id") != plan_id
        or record.get("stage") not in set(Stage)
    ):
        raise LifecycleError(
            "The lifecycle record is invalid or from another plan; retain it"
        )
    failed_from = record.get("failed_from")
    if (record["stage"] == Stage.FAILED) != (failed_from is not None) or (
        failed_from is not None and failed_from not in RESUMABLE
    ):
        raise LifecycleError(
            "The lifecycle record has an inconsistent failure; retain it"
        )
    return record


def _write(state: Path, record: dict, previous: str, detail: str) -> dict:
    record["history"].append(
        {"at": time.time(), "from": previous, "to": record["stage"], "detail": detail}
    )
    atomic_json(state / FILE, record)
    return record


def advance(
    state: Path,
    plan_id: str,
    target: Stage,
    *,
    detail: str = "",
    initial: dict | None = None,
) -> dict:
    """Move forward once; repeating the current stage changes nothing."""
    record = load(state, plan_id, initial)
    current = Stage(record["stage"])
    if current == target:
        return record
    if current == Stage.FAILED and record["failed_from"]:
        resumed = Stage(record["failed_from"])
        if target != resumed and target not in TRANSITIONS[resumed]:
            raise LifecycleError(
                f"A failed {resumed} stage cannot continue with {target}"
            )
        record["failed_from"] = None
    elif target not in TRANSITIONS[current]:
        raise LifecycleError(f"Migration cannot move from {current} to {target}")
    record["stage"] = str(target)
    return _write(state, record, str(current), detail)


def fail(
    state: Path, plan_id: str, detail: str, *, initial: dict | None = None
) -> dict:
    record = load(state, plan_id, initial)
    current = Stage(record["stage"])
    if current == Stage.FAILED:
        return record
    if Stage.FAILED not in TRANSITIONS[current]:
        raise LifecycleError(f"A {current} migration cannot be marked failed")
    record["stage"], record["failed_from"] = str(Stage.FAILED), str(current)
    return _write(state, record, str(current), detail)


def record_evidence(
    state: Path, plan_id: str, name: str, value: dict, *, initial: dict | None = None
) -> dict:
    record = load(state, plan_id, initial)
    record["evidence"][name] = value | {"at": time.time()}
    atomic_json(state / FILE, record)
    return record
