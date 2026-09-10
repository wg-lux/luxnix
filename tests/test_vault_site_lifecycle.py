"""Executable lifecycle tests use a recording API, never a live Vault."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "site_lifecycle", ROOT / "scripts/vault/site_lifecycle.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SITE = "gc-06.example.net"
ROLE = module.identity(SITE)
POLICY = "lx-hub-" + ROLE


class RecordingVault:
    def __init__(self, failure=None):
        self.calls = []
        self.failure = failure
        self.version = 4
        self.data = {"shared_secret": "test-only-retiring", "retained": "metadata"}

    def call(self, verb, path, payload=None, **kwargs):
        self.calls.append((verb, path, payload))
        if path == self.failure:
            raise module.LifecycleError("controlled API failure")
        if "/roles/" in path:
            return {"data": {"allowed_domains": [SITE]}}
        if path.endswith("/secret-id") and verb == "list":
            return {"data": {"keys": ["test-id-accessor"]}}
        if path == "auth/token/accessors":
            return {"data": {"keys": ["mine", "other"]}}
        if path == "auth/token/lookup-accessor":
            return {
                "data": {
                    "policies": [POLICY]
                    if payload["accessor"] == "mine"
                    else ["unrelated"],
                    "meta": {"role_name": ROLE},
                }
            }
        if "/data/nodes/" in path:
            if verb == "write":
                assert payload["options"]["cas"] == self.version
                self.version += 1
                self.data = payload["data"].copy()
                return {}
            return {
                "data": {
                    "metadata": {"version": self.version},
                    "data": self.data.copy(),
                }
            }
        if path.endswith("/cert/ca"):
            return {"data": {"certificate": "test-only-public-ca"}}
        if path.endswith("/role-id"):
            return {"data": {"role_id": "test-only-role-id"}}
        if path.endswith("/secret-id"):
            return {"data": {"secret_id": "test-only-replacement"}}
        return {}


def lifecycle(tmp_path, monkeypatch, failure=None):
    ca = tmp_path / "ca.pem"
    ca.write_text("test-only-public-ca")
    monkeypatch.setattr(module.ssl, "PEM_cert_to_DER_cert", lambda value: b"public-ca")
    vault = RecordingVault(failure)
    return module.Lifecycle(vault, tmp_path, "kv", server_ca=ca), vault


def test_contain_denies_before_revocation_and_scopes_tokens(tmp_path, monkeypatch):
    handler, vault = lifecycle(tmp_path, monkeypatch)
    handler.contain(SITE)
    assert vault.calls[1] == (
        "write",
        "sys/policies/acl/" + POLICY,
        {"policy": 'path "*" { capabilities = ["deny"] }'},
    )
    revoked = [
        payload
        for _, path, payload in vault.calls
        if path == "auth/token/revoke-accessor"
    ]
    assert revoked == [{"accessor": "mine"}]
    assert json.loads((tmp_path / ROLE).read_text())["phase"] == "contained"


@pytest.mark.parametrize(
    "failure",
    [
        "sys/policies/acl/" + POLICY,
        "auth/approle/role/" + ROLE + "/secret-id-accessor/destroy",
        "auth/token/revoke-accessor",
    ],
)
def test_revocation_failures_keep_marker_and_block_rotation(
    tmp_path, monkeypatch, failure
):
    handler, vault = lifecycle(tmp_path, monkeypatch, failure)
    with pytest.raises(module.LifecycleError):
        handler.contain(SITE)
    assert (tmp_path / ROLE).exists()
    with pytest.raises(module.LifecycleError):
        handler.rotate(SITE, tmp_path / "bundle")
    with pytest.raises(module.LifecycleError):
        handler.resume(SITE)


def test_rotation_cas_preserves_fields_and_exports_installer_bundle(
    tmp_path, monkeypatch
):
    handler, vault = lifecycle(tmp_path, monkeypatch)
    handler.contain(SITE)
    handler.rotate(SITE, tmp_path / "bundle")
    bundle = tmp_path / "bundle"
    assert {p.name for p in bundle.iterdir()} == {
        "approle_role_id",
        "approle_secret_id",
        "source-node-secret",
        "vault-server-ca.pem",
        "vault-server-ca.sha256",
        "client-ca.pem",
    }
    assert vault.version == 5 and vault.data["retained"] == "metadata"
    assert vault.data["shared_secret"] != "test-only-retiring"
    assert all(p.stat().st_mode & 0o777 == 0o400 for p in bundle.iterdir())
    assert json.loads((tmp_path / ROLE).read_text())["phase"] == "rotated"
    handler.resume(SITE)
    assert not (tmp_path / ROLE).exists()
    # Resume does not silently restore policies: explicit reconciliation follows.
    assert sum(path.startswith("sys/policies") for _, path, _ in vault.calls) == 1


def test_partial_rotation_requires_fresh_containment(tmp_path, monkeypatch):
    handler, vault = lifecycle(tmp_path, monkeypatch)
    handler.contain(SITE)
    vault.failure = "auth/approle/role/" + ROLE + "/secret-id"
    with pytest.raises(module.LifecycleError):
        handler.rotate(SITE, tmp_path / "bundle")
    assert vault.version == 5
    with pytest.raises(module.LifecycleError):
        handler.resume(SITE)


@pytest.mark.parametrize(
    "site", ["*", "gc-06", "../bad", "GC-06.example.net", "a..net", "-a.example.net"]
)
def test_exact_scope_required(site):
    with pytest.raises(module.LifecycleError):
        module.identity(site)


def test_api_failure_is_redacted_and_credentials_go_to_stdin(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=2, stdout="", stderr="permission denied test-only-sensitive"
        )

    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(module.LifecycleError) as error:
        module.Vault().call(
            "write", "auth/token/revoke-accessor", {"accessor": "test-only-sensitive"}
        )
    assert "test-only-sensitive" not in str(error.value)
    assert "test-only-sensitive" not in repr(calls[0][0])
    assert "test-only-sensitive" in calls[0][1]["input"]
    with pytest.raises(module.LifecycleError):
        module.Vault().call("list", "auth/token/accessors", empty=True)


def test_reconciliation_and_enrollment_check_containment_before_mutation():
    source = (ROOT / "modules/nixos/luxnix/vault/default.nix").read_text()
    reconcile = source.split("      reconcile_site() {", 1)[1].split(
        "  hubSiteLifecycleTool", 1
    )[0]
    assert reconcile.index("site is contained") < reconcile.index("vault write")
    enroll = source.split("  hubSiteEnrollmentTool =", 1)[1].split(
        "  managedServerTlsTool", 1
    )[0]
    assert (
        enroll.index("flock -x 9")
        < enroll.index("site is contained")
        < enroll.index("vault write -field=secret_id")
    )


def test_alias_collision_cannot_rotate_or_resume_other_site(tmp_path, monkeypatch):
    handler, vault = lifecycle(tmp_path, monkeypatch)
    handler.contain(SITE)
    alias = "gc.06.example.net"
    assert module.identity(alias) == ROLE
    with pytest.raises(module.LifecycleError):
        handler.contain(alias)
    with pytest.raises(module.LifecycleError):
        handler.rotate(alias, tmp_path / "alias-bundle")
    with pytest.raises(module.LifecycleError):
        handler.resume(alias)


def test_bodyless_write_success_is_not_parsed_as_json(monkeypatch):
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="Success! Data written to: auth/token/revoke-accessor\n",
            stderr="",
        ),
    )
    assert module.Vault().call("write", "auth/token/revoke-accessor", {}) == {}
