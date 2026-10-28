"""Host enrollment logic with mocked system calls (evidence class unit only).

Real TPM, cryptsetup and OpenBao behavior is exercised by
tests/nixtest/openbao_local_vm_test.nix.
"""

import base64
import fcntl
import json
from types import SimpleNamespace

import pytest

from lx_administration.storage import openbao_enroll as enroll
from lx_administration.storage import openbao_local as local

UUID = "11111111-1111-1111-1111-111111111111"
KEY = base64.b64encode(bytes(range(32))).decode()


@pytest.fixture
def host(tmp_path, monkeypatch):
    boot = tmp_path / "bootstrap"
    paths = {
        "BOOT": boot,
        "RAFT": tmp_path / "raft.db",
        "SEAL": boot / "seal.cred",
        "UNLOCK": boot / "volume-unlock.cred",
        "PENDING": boot / "pending-enrollment.cred",
        "PENDING_PROVISIONER": boot / "pending-provisioner.cred",
        "LOCK": tmp_path / "lock",
    }
    for name, value in paths.items():
        monkeypatch.setattr(enroll, name, value)
    sealed = {}

    def seal(name, plaintext, target):
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b"ciphertext")
        sealed[target.name] = plaintext

    monkeypatch.setattr(enroll, "seal_credential", seal)
    monkeypatch.setattr(enroll, "unseal_credential", lambda name, source: sealed[source.name])
    tpm = SimpleNamespace(present=True)
    monkeypatch.setattr(enroll.subprocess, "run", lambda args, **kw: SimpleNamespace(
        returncode=0 if tpm.present else 1, stdout=b"", stderr=b""))
    calls = []

    def api_call(method, path, data=None, token=None, timeout=5):
        calls.append((method, path))
        if path == "sys/seal-status":
            return {"initialized": True, "sealed": False}
        raise AssertionError(f"unexpected API call {method} {path}")

    client = {"call": api_call, "DeniedError": RuntimeError, "wait_unsealed": lambda t: None,
              "login": lambda c: "token"}
    platform = {"physical_tpm": True, "secure_boot": True, "secure_boot_required": True}
    monkeypatch.setattr(
        local, "platform_status", lambda: dict(platform, tpm2=tpm.present)
    )
    client.update(platform_status=local.platform_status,
                  platform_preflight=local.platform_preflight)
    instance = enroll.Host("gc-10", client)
    return SimpleNamespace(host=instance, paths=paths, sealed=sealed,
                           tpm=tpm, calls=calls, platform=platform)


def test_preflight_fails_closed_without_tpm_or_secure_boot(host):
    host.tpm.present = False
    with pytest.raises(enroll.EnrollError, match="tpm-missing"):
        host.host.preflight()
    host.tpm.present = True
    host.platform["secure_boot"] = False
    with pytest.raises(enroll.EnrollError, match="secure-boot-disabled"):
        host.host.preflight()
    # Mutating phases repeat the live check; nothing is sealed.
    with pytest.raises(enroll.EnrollError, match="secure-boot-disabled"):
        host.host.seal({"seal_key": KEY})
    assert host.sealed == {}


def test_seal_is_idempotent_and_never_replaced(host):
    host.host.seal({"seal_key": KEY})
    host.host.seal({"seal_key": KEY})
    assert host.sealed["seal.cred"] == bytes(range(32))
    other = base64.b64encode(bytes(32)).decode()
    with pytest.raises(enroll.EnrollError, match="never replaced"):
        host.host.seal({"seal_key": other})
    assert host.sealed["seal.cred"] == bytes(range(32))


def test_seal_refuses_existing_store_without_credential(host):
    host.paths["RAFT"].write_bytes(b"")
    with pytest.raises(enroll.EnrollError, match="recovery"):
        host.host.seal({"seal_key": KEY})
    assert host.sealed == {}


def test_initialized_store_without_pending_escrow_is_never_reinitialized(host, monkeypatch):
    host.host.seal({"seal_key": KEY})
    host.paths["RAFT"].write_bytes(b"")
    monkeypatch.setattr(enroll, "run", lambda *a, **k: b"")
    with pytest.raises(enroll.EnrollError, match="interrupted-initialization"):
        host.host.initialize()
    assert ("POST", "sys/init") not in host.calls


def test_confirm_rejects_unescrowed_material_before_any_revocation(host):
    host.paths["BOOT"].mkdir()
    for path, name, value in [
        (host.paths["PENDING"], "pending-enrollment.cred", {"root_token": "root", "recovery_key": "r"}),
        (host.paths["PENDING_PROVISIONER"], "pending-provisioner.cred",
         {"role_id": "a", "secret_id": "b", "accessor": "c"}),
    ]:
        path.write_bytes(b"ciphertext")
        host.sealed[name] = json.dumps(value).encode()
    wrong = enroll.escrow_digest({"recovery_key": "other", "provisioner": {}})
    with pytest.raises(enroll.EnrollError, match="does not match"):
        host.host.confirm({"escrow_sha256": wrong})
    assert host.calls == []
    assert host.paths["PENDING"].exists()


def test_plan_and_uuid_mismatch_never_mutate(host, tmp_path, monkeypatch):
    container = tmp_path / "data.luks"
    container.write_bytes(b"preserved")
    commands = []
    metadata = {"keyslots": {"0": {}, "1": {}},
                "tokens": {"0": {"type": "systemd-tpm2", "keyslots": ["1"]}}}

    def run(*args, **kwargs):
        commands.append(args[1])
        if args[1] == "luksUUID":
            return UUID.encode() + b"\n"
        return json.dumps(metadata).encode()

    monkeypatch.setattr(enroll, "run", run)
    plan = host.host.plan_volume("data", str(container), UUID)
    assert plan["changes"] == ["add OpenBao keyslot and luxnix-openbao token",
                               "remove systemd-tpm2 token 0 and keyslots 1"]
    assert set(commands) == {"luksUUID", "luksDump"}
    with pytest.raises(enroll.EnrollError, match="does not match"):
        host.host.plan_volume("data", str(container), "22222222-2222-2222-2222-222222222222")
    with pytest.raises(enroll.EnrollError, match="volume-missing"):
        host.host.plan_volume("data", str(tmp_path / "absent.luks"), UUID)
    assert container.read_bytes() == b"preserved"


def test_convert_requires_completed_enrollment(host, tmp_path):
    with pytest.raises(enroll.EnrollError, match="Enrollment must be complete"):
        host.host.convert_volume("data", str(tmp_path / "x"), UUID, {})


def test_concurrent_mutation_is_rejected(host, monkeypatch, capsys):
    monkeypatch.setattr(enroll.os, "geteuid", lambda: 0)
    monkeypatch.setattr(enroll.runpy, "run_path", lambda _: host.host.client)
    monkeypatch.setattr(enroll.sys, "stdin", SimpleNamespace(buffer=SimpleNamespace(
        read=lambda n: json.dumps({"seal_key": KEY}).encode())))
    with open(host.paths["LOCK"], "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert enroll.main(["--client", "c", "--hostname", "gc-10", "seal"]) == 1
    assert "conflict" in capsys.readouterr().err
    assert host.sealed == {}


def test_missing_record_for_enrolled_volume_is_never_recreated(host, monkeypatch):
    host.paths['RAFT'].touch()
    host.paths['UNLOCK'].parent.mkdir(exist_ok=True)
    host.paths['UNLOCK'].touch()
    monkeypatch.setattr(host.host, '_volume', lambda *args: host.paths['RAFT'])
    monkeypatch.setattr(enroll, '_metadata', lambda path: {
        'tokens': {'1': {'type': enroll.TOKEN_TYPE, 'keyslots': ['1']}}})
    calls = []
    def api(method, path, data=None, token=None):
        calls.append((method, path))
        if method == 'GET':
            raise enroll.EnrollError('record absent')
        assert path == 'auth/token/revoke-self'
        return {}
    monkeypatch.setattr(host.host, 'api', api)
    with pytest.raises(enroll.EnrollError, match='never replace'):
        host.host.volume_record('data', UUID, {'role_id': 'test'}, '/test.luks')
    assert not any(method == 'POST' and path.startswith('volume-release') for method, path in calls)
    assert calls[-1] == ('POST', 'auth/token/revoke-self')


@pytest.mark.parametrize(
    "phase", ["seal", "initialize", "confirm", "convert_volume", "rotate_unlock"]
)
@pytest.mark.parametrize("missing", ["physical_tpm", "secure_boot"])
def test_every_mutation_rejects_platform_before_writes(host, phase, missing, tmp_path):
    host.platform[missing] = False
    args = {"seal": ({"seal_key": KEY},), "initialize": (), "confirm": ({},),
            "convert_volume": ("data", str(tmp_path / "absent"), UUID, {}),
            "rotate_unlock": ({},)}
    reason = "tpm-not-physical" if missing == "physical_tpm" else "secure-boot-disabled"
    with pytest.raises(enroll.EnrollError, match=reason):
        getattr(host.host, phase)(*args[phase])
    assert host.calls == []
    assert host.sealed == {}
    assert not host.paths["BOOT"].exists()


# Passphrase seal: no platform gate; the boot passphrase wraps the escrowed key.

BOOT_PASSPHRASE = "correct horse battery"


@pytest.fixture
def passphrase_host(host, tmp_path, monkeypatch):
    monkeypatch.setattr(enroll, "SEAL_WRAP", host.paths["BOOT"] / "seal-passphrase.json")
    monkeypatch.setattr(enroll, "SEAL_RUNTIME", tmp_path / "run" / "seal.key")
    bindings = []

    def seal(name, plaintext, target, key="tpm2"):
        bindings.append(key)
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b"ciphertext")
        host.sealed[target.name] = plaintext
    monkeypatch.setattr(enroll, "seal_credential", seal)
    client = dict(host.host.client, wrap_seal_key=local.wrap_seal_key,
                  unwrap_seal_key=local.unwrap_seal_key, write_private=local.write_private,
                  read_private=lambda path: path.read_bytes(), stage_verified_seal=local.stage_verified_seal)
    monkeypatch.setattr(local, "read_private", lambda path: path.read_bytes())
    host.tpm.present = False
    host.platform.update(secure_boot=False, physical_tpm=False)
    return SimpleNamespace(host=enroll.Host("gc-10", client, "passphrase"), bindings=bindings,
                           tmp=tmp_path)


def test_passphrase_seal_needs_no_tpm_or_secure_boot(passphrase_host):
    status = passphrase_host.host.preflight()
    assert status["seal"] == "passphrase" and not status["secure_boot"]


def test_passphrase_seal_wraps_escrowed_key_and_stages_it(passphrase_host):
    result = passphrase_host.host.seal({"seal_key": KEY, "seal_passphrase": BOOT_PASSPHRASE})
    assert result == {"sealed": True}
    record = json.loads(enroll.SEAL_WRAP.read_bytes())
    assert local.unwrap_seal_key(record, BOOT_PASSPHRASE.encode()) == base64.b64decode(KEY)
    assert BOOT_PASSPHRASE not in enroll.SEAL_WRAP.read_text() and KEY not in enroll.SEAL_WRAP.read_text()
    assert enroll.SEAL_RUNTIME.read_bytes() == base64.b64decode(KEY)
    # A rerun verifies instead of replacing the record.
    before = enroll.SEAL_WRAP.read_bytes()
    passphrase_host.host.seal({"seal_key": KEY, "seal_passphrase": BOOT_PASSPHRASE})
    assert enroll.SEAL_WRAP.read_bytes() == before


def test_passphrase_seal_rerun_rejects_other_passphrase_or_key(passphrase_host):
    host = passphrase_host.host
    host.seal({"seal_key": KEY, "seal_passphrase": BOOT_PASSPHRASE})
    with pytest.raises(enroll.EnrollError, match="seal-passphrase-rejected"):
        host.seal({"seal_key": KEY, "seal_passphrase": "another long passphrase"})
    other = base64.b64encode(bytes(32)).decode()
    with pytest.raises(enroll.EnrollError, match="different key"):
        host.seal({"seal_key": other, "seal_passphrase": BOOT_PASSPHRASE})


def test_passphrase_seal_refuses_store_without_record_and_weak_passphrase(passphrase_host):
    with pytest.raises(enroll.EnrollError, match="at least"):
        passphrase_host.host.seal({"seal_key": KEY, "seal_passphrase": "short"})
    enroll.RAFT.write_bytes(b"store")
    with pytest.raises(enroll.EnrollError, match="without its seal record"):
        passphrase_host.host.seal({"seal_key": KEY, "seal_passphrase": BOOT_PASSPHRASE})


def test_passphrase_seal_binds_bootstrap_credentials_to_host_key(passphrase_host):
    passphrase_host.host._seal("volume.unlock", b"{}", enroll.UNLOCK)
    assert passphrase_host.bindings == ["host"]


def test_existing_tpm_store_is_not_enrolled_under_passphrase_mode(passphrase_host):
    enroll.RAFT.touch()
    enroll.BOOT.mkdir()
    enroll.SEAL.write_bytes(b"existing TPM credential")
    enroll.UNLOCK.touch()
    status = passphrase_host.host.status()
    assert not status["enrolled"] and not status["seal_credential"]
    with pytest.raises(enroll.EnrollError, match="use recovery"):
        passphrase_host.host.seal({"seal_key": KEY, "seal_passphrase": BOOT_PASSPHRASE})


def test_enrollment_rejects_foreign_staged_key(passphrase_host):
    local.write_private(enroll.SEAL_RUNTIME, bytes(32))
    with pytest.raises(ValueError, match="does not match"):
        passphrase_host.host.seal({"seal_key": KEY, "seal_passphrase": BOOT_PASSPHRASE})
