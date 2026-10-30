"""Convergence and failure boundaries without production secret access."""

import copy
import json

import pytest

from lx_administration.storage import bao_migration as migration

RECORD = {
    "id": "application",
    "source_mount": "kv",
    "source_path": "app",
    "target_mount": "kv",
    "target_path": "app",
    "mode": "immutable",
    "required_fields": ["key"],
}


class Store:
    def __init__(self, values=None, active=True):
        self.values = copy.deepcopy(values or {})
        self.is_active = active
        self.writes = []
        self.after_write = None
        self.before_write = None

    def active(self):
        if isinstance(self.is_active, Exception):
            raise self.is_active
        return self.is_active

    def read(self, path):
        if path not in self.values:
            raise migration.ApiError(404)
        return copy.deepcopy(self.values[path])

    def call(self, method, path, data):
        assert method == "POST"
        if self.before_write:
            self.before_write()
        current = (
            self.values.get(path, {})
            .get("data", {})
            .get("metadata", {})
            .get("version", 0)
        )
        if current != data["options"]["cas"]:
            raise migration.ApiError(400)
        self.values[path] = record(data["data"], current + 1)
        self.writes.append(path)
        if self.after_write:
            raise self.after_write
        return {}


def record(data, version=1):
    return {
        "data": {
            "data": data,
            "metadata": {"version": version, "destroyed": False, "deletion_time": ""},
        }
    }


def source():
    return Store({"kv/data/app": record({"key": "synthetic-key", "old": [1, 2]})})


def test_preview_create_repeat_and_recover_lost_acknowledgement():
    origin, target = source(), Store()
    result = migration.reconcile(origin, target, [RECORD])
    assert result["records"][0]["action"] == "create"
    assert target.writes == []
    target.after_write = migration.Unavailable("lost acknowledgement")
    migration.reconcile(origin, target, [RECORD], apply=True)
    result = migration.reconcile(origin, target, [RECORD], apply=True)
    assert result["records"][0]["action"] == "unchanged"
    assert len(target.writes) == 1
    assert "synthetic-key" not in json.dumps(result)


@pytest.mark.parametrize(
    "origin", [None, Store(active=False), Store(active=migration.Unavailable("gone"))]
)
def test_absent_or_inactive_vault_preserves_verified_target(origin):
    target = source()
    result = migration.reconcile(origin, target, [RECORD], apply=True)
    assert result["mode"] == "target_only"
    assert result["records"][0]["action"] == "verified_target"
    assert target.writes == []


@pytest.mark.parametrize(
    "origin", [None, Store(active=False), Store(active=migration.Unavailable("gone"))]
)
def test_absent_vault_cannot_hide_missing_target(origin):
    with pytest.raises(migration.MigrationError, match="missing"):
        migration.reconcile(origin, Store(), [RECORD], apply=True)


@pytest.mark.parametrize(
    "error", [migration.ApiError(403), migration.MigrationError("TLS failed")]
)
def test_authentication_and_tls_errors_never_become_absence(error):
    with pytest.raises(migration.MigrationError):
        migration.reconcile(Store(active=error), source(), [RECORD], apply=True)


def test_all_records_validated_before_any_write():
    target = Store()
    second = {
        **RECORD,
        "id": "missing",
        "source_path": "missing",
        "target_path": "missing",
    }
    with pytest.raises(migration.MigrationError, match="source record"):
        migration.reconcile(source(), target, [RECORD, second], apply=True)
    assert target.writes == []


def test_immutable_conflict_and_explicit_source_authority():
    target = Store({"kv/data/app": record({"key": "old"}, 3)})
    with pytest.raises(migration.MigrationError, match="Immutable"):
        migration.reconcile(source(), target, [RECORD], apply=True)
    assert target.writes == []
    result = migration.reconcile(
        source(), target, [{**RECORD, "mode": "source_authoritative"}], apply=True
    )
    assert result["records"][0]["action"] == "update"
    assert target.values["kv/data/app"]["data"]["metadata"]["version"] == 4


def test_concurrent_distinct_write_is_not_overwritten():
    target = Store()
    target.before_write = lambda: target.values.update(
        {"kv/data/app": record({"key": "other"})}
    )
    with pytest.raises(migration.MigrationError, match="Concurrent"):
        migration.reconcile(source(), target, [RECORD], apply=True)
    assert target.values["kv/data/app"]["data"]["data"]["key"] == "other"
    assert target.writes == []


def test_source_change_before_write_requires_new_plan():
    origin, target = source(), Store()
    original = origin.read
    calls = []

    def read(path):
        calls.append(path)
        return original(path) if len(calls) == 1 else record({"key": "changed"}, 2)

    origin.read = read
    with pytest.raises(migration.MigrationError, match="changed during"):
        migration.reconcile(origin, target, [RECORD], apply=True)
    assert target.writes == []


def test_deleted_record_is_never_resurrected():
    target = Store({"kv/metadata/app": {"data": {"current_version": 3}}})
    with pytest.raises(migration.MigrationError, match="deleted"):
        migration.reconcile(source(), target, [RECORD], apply=True)
    assert target.writes == []


def test_target_unavailability_always_fails():
    with pytest.raises(migration.MigrationError):
        migration.reconcile(None, Store(active=False), [RECORD], apply=True)


@pytest.mark.parametrize(
    "change",
    [
        {"source_path": "../app"},
        {"mode": "overwrite"},
        {"required_fields": []},
        {"target_mount": "kv?redirect=evil"},
        {"id": "../bad"},
    ],
)
def test_manifest_rejects_unsafe_or_ambiguous_inputs(change):
    endpoint = {
        "url": "https://bao.example",
        "ca_file": "/public/ca.pem",
        "token_file": "/run/token",
    }
    with pytest.raises(migration.MigrationError):
        migration.validate(
            {
                "version": 1,
                "source": None,
                "target": endpoint,
                "records": [{**RECORD, **change}],
            }
        )


def test_partial_wave_resumes_without_rewriting_completed_record():
    origin, target = source(), Store()
    origin.values["kv/data/second"] = record({"key": "second-key"})
    second = {
        **RECORD,
        "id": "second",
        "source_path": "second",
        "target_path": "second",
    }
    call = target.call

    def interrupted(method, path, data):
        if path.endswith("/second"):
            raise migration.Unavailable("interrupted before write")
        return call(method, path, data)

    target.call = interrupted
    with pytest.raises(migration.MigrationError):
        migration.reconcile(origin, target, [RECORD, second], apply=True)
    assert target.writes == ["kv/data/app"]
    target.call = call
    result = migration.reconcile(origin, target, [RECORD, second], apply=True)
    assert [item["action"] for item in result["records"]] == ["unchanged", "create"]
    assert target.writes == ["kv/data/app", "kv/data/second"]
    assert target.values["kv/data/app"]["data"]["metadata"]["version"] == 1


def test_json_value_types_are_not_conflated():
    assert not migration.same_data((1, {"key": True}), (1, {"key": 1}))


def test_malformed_health_is_not_treated_as_retirement():
    client = object.__new__(migration.Client)
    client.call = lambda *args, **kwargs: {"initialized": True}
    with pytest.raises(migration.MigrationError, match="malformed health"):
        migration.reconcile(client, source(), [RECORD], apply=True)


def test_target_only_rejects_non_json_secret_data():
    target = Store({"kv/data/app": record({"key": float("nan")})})
    with pytest.raises(migration.MigrationError, match="malformed"):
        migration.reconcile(None, target, [RECORD], apply=True)


def test_unreachable_network_is_optional_source_not_configuration_failure(monkeypatch):
    client = object.__new__(migration.Client)
    client.url = migration.urlsplit("https://vault.example")
    client.context = None

    class Offline:
        def request(self, *args, **kwargs):
            raise OSError(101, "Network is unreachable")

        def close(self):
            pass

    monkeypatch.setattr(
        migration.http.client, "HTTPSConnection", lambda *a, **kw: Offline()
    )
    result = migration.reconcile(client, source(), [RECORD], apply=True)
    assert result["mode"] == "target_only"
