"""Disposable guest fixture driving the real enrollment tool.

Never print API bodies or credentials. All material is synthetic and stays in
the guest; only pass/fail and the tool's ERROR line reach the driver log.
"""

import base64
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

spec = importlib.util.spec_from_file_location("client", "/etc/test-client.py")
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)
ROOT = Path("/run/local-test")
BOOT = Path("/var/lib/openbao-bootstrap")
CONTAINER = Path("/var/lib/test.luks")
UUID = "11111111-1111-1111-1111-111111111111"
VOLUME = ["--volume", "test", "--container", str(CONTAINER), "--luks-uuid", UUID]


def run(*args, data=None):
    result = subprocess.run(args, input=data, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} {args[1] if len(args) > 1 else ''} failed")
    return result.stdout


def tool(*args, request=None, reason=None):
    """Run luxnix-openbao-local; with reason, require a failure naming it."""
    data = b"" if request is None else json.dumps(request).encode()
    result = subprocess.run(
        ["python", "-I", "/etc/enrollment.py", "--client", "/etc/test-client.py",
         "--hostname", "server", *args], input=data, capture_output=True
    )
    error = result.stderr.decode(errors="replace").strip().splitlines()[-1:] or [""]
    if reason is not None:
        assert result.returncode != 0, f"{args[0]} unexpectedly succeeded"
        assert reason in error[0], f"{args[0]} failed for another reason: {error[0]}"
        return None
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {error[0]}")
    return json.loads(result.stdout)


def private(name):
    return json.loads((ROOT / name).read_text())


def save(name, value):
    (ROOT / name).write_text(json.dumps(value))


def dump():
    return json.loads(
        run("cryptsetup", "luksDump", "--dump-json-metadata", str(CONTAINER))
    )


def data_digest(mapping):
    """Mount read-only and hash the synthetic payload."""
    Path("/mnt/check").mkdir(parents=True, exist_ok=True)
    run("mount", "-o", "ro", f"/dev/mapper/{mapping}", "/mnt/check")
    try:
        return hashlib.sha256(Path("/mnt/check/payload").read_bytes()).hexdigest()
    finally:
        run("umount", "/mnt/check")


def denied(method, path, token):
    try:
        client.call(method, path, token=token)
    except client.DeniedError:
        return True
    return False


os.umask(0o077)
command = sys.argv[1]
if command == "prepare":
    ROOT.mkdir()
    seal_key = secrets.token_bytes(32)
    (ROOT / "seal.key").write_bytes(seal_key)
    save("seal.json", {"seal_key": base64.b64encode(seal_key).decode()})
    # Negative fixtures for the credential validator.
    for key, pcr, target in (
        ("host", "7", ROOT / "host.cred"),
        ("tpm2", "0", ROOT / "pcr0.cred"),
    ):
        run(
            "systemd-creds",
            "encrypt",
            f"--with-key={key}",
            f"--tpm2-pcrs={pcr}",
            "--name=seal.key",
            str(ROOT / "seal.key"),
            str(target),
        )
    # A pre-existing legacy container: recovery passphrase plus a PCR 7 systemd-tpm2 token.
    recovery = secrets.token_hex(32)
    (ROOT / "recovery").write_text(recovery)
    run("truncate", "-s", "64M", str(CONTAINER))
    run(
        "cryptsetup",
        "luksFormat",
        "--type",
        "luks2",
        "--batch-mode",
        "--uuid",
        UUID,
        "--key-file",
        str(ROOT / "recovery"),
        str(CONTAINER),
    )
    run(
        "systemd-cryptenroll",
        f"--unlock-key-file={ROOT / 'recovery'}",
        "--tpm2-device=auto",
        "--tpm2-pcrs=7",
        str(CONTAINER),
    )
    run(
        "cryptsetup",
        "open",
        "--key-file",
        str(ROOT / "recovery"),
        str(CONTAINER),
        "legacy",
    )
    run("mkfs.ext4", "-q", "/dev/mapper/legacy")
    Path("/mnt/legacy").mkdir(parents=True, exist_ok=True)
    run("mount", "/dev/mapper/legacy", "/mnt/legacy")
    Path("/mnt/legacy/payload").write_bytes(secrets.token_bytes(4096))
    run("umount", "/mnt/legacy")
    digest = data_digest("legacy")
    run("cryptsetup", "close", "legacy")
    before = dump()
    save(
        "before.json",
        {
            "digest": digest,
            "keyslots": sorted(before["keyslots"]),
            "tokens": [t["type"] for t in before["tokens"].values()],
            "tpm2_keyslots": [
                slot
                for t in before["tokens"].values()
                if t["type"] == "systemd-tpm2"
                for slot in t["keyslots"]
            ],
        },
    )
    assert "systemd-tpm2" in private("before.json")["tokens"]

elif command == "enroll":
    # Production admission is tested separately; this is the isolated software-TPM client.
    tool("convert-volume", *VOLUME, request={}, reason="Enrollment must be complete")
    tool("initialize", reason="Seal credential missing")
    seal = private("seal.json")
    tool("seal", request=seal)
    tool("seal", request=seal)
    tool(
        "seal",
        request={"seal_key": base64.b64encode(bytes(32)).decode()},
        reason="never replaced",
    )
    # Concurrent mutations of the same host are rejected, not interleaved.
    with open("/run/lock/luxnix-operator-migration", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        tool("initialize", reason="conflict")
    first = tool("initialize")["escrow"]
    # An interruption before confirmation resumes with identical escrow material.
    assert tool("initialize")["escrow"] == first
    save("escrow.json", first)
    root_token = json.loads(
        run(
            "systemd-creds",
            "decrypt",
            "--name=pending.json",
            str(BOOT / "pending-enrollment.cred"),
            "-",
        )
    )["root_token"]
    assert not denied("GET", "auth/token/lookup-self", root_token)
    tool("confirm", request={"escrow_sha256": "0" * 64}, reason="does not match")
    digest = hashlib.sha256(json.dumps(first, sort_keys=True).encode()).hexdigest()
    tool("confirm", request={"escrow_sha256": digest})
    assert denied("GET", "auth/token/lookup-self", root_token), (
        "root token survived confirmation"
    )
    assert not (BOOT / "pending-enrollment.cred").exists()
    assert not (BOOT / "pending-provisioner.cred").exists()
    tool("initialize", reason="never reinitializes")
    status = tool("status")
    assert status["enrolled"] and not status["pending_escrow"], status

elif command == "adopt":
    escrow = private("escrow.json")
    request = {
        "recovery_passphrase": (ROOT / "recovery").read_text(),
        "provisioner": escrow["provisioner"],
    }
    plan = tool("plan-volume", *VOLUME)
    assert plan["openbao_keyslot"] is None and len(plan["changes"]) == 2, plan
    tool(
        "convert-volume",
        *VOLUME,
        request=dict(request, recovery_passphrase="0" * 64),
        reason="recovery-passphrase-rejected",
    )
    wrong_uuid = VOLUME[:-1] + ["22222222-2222-2222-2222-222222222222"]
    tool("convert-volume", *wrong_uuid, request=request, reason="does not match")
    results = [tool("convert-volume", *VOLUME, request=request) for _ in range(3)]
    slot = results[0]["openbao_keyslot"]
    assert all(r["openbao_keyslot"] == slot for r in results), results
    after = dump()
    before = private("before.json")
    types = [t["type"] for t in after["tokens"].values()]
    assert types == ["luxnix-openbao"], types
    # Recovery slot kept, legacy TPM slot gone, exactly one OpenBao slot.
    assert (
        len(after["keyslots"]) == 2
        and results[0]["recovery_keyslot"] in after["keyslots"]
    )
    assert run("cryptsetup", "luksUUID", str(CONTAINER)).decode().strip() == UUID
    run(
        "cryptsetup",
        "open",
        "--test-passphrase",
        "--key-file",
        str(ROOT / "recovery"),
        str(CONTAINER),
    )
    assert tool("plan-volume", *VOLUME)["changes"] == []
    removed = results[0]["removed_tpm2_keyslots"]
    assert removed and set(removed) == set(before["tpm2_keyslots"]), results[0]
    assert not set(removed) & set(after["keyslots"])
    assert all(r["removed_tpm2_keyslots"] == [] for r in results[1:]), results

elif command == "provision":
    # This guest has a real swtpm but no Secure Boot keys. Exercise the real
    # provisioning phases directly; the production firmware gate must reject.
    sys.path.insert(0, "/etc")
    import migration
    import enrollment
    try:
        migration.require_secure_boot()
    except migration.MigrationError:
        pass
    else:
        raise AssertionError("Unsigned guest unexpectedly passed Secure Boot")
    native_uuid = "33333333-3333-3333-3333-333333333333"
    record = {"machine_id": Path("/etc/machine-id").read_text().strip(),
              "host": "server", "volume": "fresh", "container": "/var/lib/fresh.luks",
              "luks_uuid": native_uuid, "origin": "new",
              "recovery_passphrase": secrets.token_hex(32),
              "provisioner": private("escrow.json")["provisioner"]}
    host = enrollment.Host("server", vars(client))
    task = migration.Migration({"unlockMethod": "local-openbao", "binds": {},
        "volumes": {"fresh": {"container": record["container"], "device": "/dev/mapper/fresh",
                              "luksUUID": native_uuid, "minimumSizeMiB": 64}}}, None)
    # Fault after keyslot enrollment but before filesystem creation, then resume.
    original = migration.run
    def interrupted(*args, **kwargs):
        if args[0] == "mkfs.ext4":
            raise migration.MigrationError("injected before filesystem")
        return original(*args, **kwargs)
    migration.run = interrupted
    try:
        task.provision_local("fresh", record, host, record["recovery_passphrase"].encode(), native_uuid)
    except migration.MigrationError as exc:
        assert "injected" in str(exc)
    else:
        raise AssertionError("Provisioning interruption not exercised")
    migration.run = original
    for _ in range(2):
        task.provision_local("fresh", record, host, record["recovery_passphrase"].encode(), native_uuid)
    metadata = json.loads(run("cryptsetup", "luksDump", "--dump-json-metadata", record["container"]))
    assert len(metadata["keyslots"]) == 2
    assert [t["type"] for t in metadata["tokens"].values()] == ["luxnix-openbao"]
    assert run("blkid", "-s", "TYPE", "-o", "value", "/dev/mapper/fresh").strip() == b"ext4"
    run("cryptsetup", "close", "fresh")

elif command == "check-data":
    assert data_digest("test") == private("before.json")["digest"]

elif command == "rotate":
    old = json.loads(
        run(
            "systemd-creds",
            "decrypt",
            "--name=volume.unlock",
            str(BOOT / "volume-unlock.cred"),
            "-",
        )
    )
    client.login(json.dumps(old).encode())
    tool(
        "rotate-unlock", request={"provisioner": private("escrow.json")["provisioner"]}
    )
    try:
        client.login(json.dumps(old).encode())
    except ValueError:
        pass
    else:
        raise AssertionError("Rotated-out SecretID still logs in")
    # The old provisioner copy in a stale request is not an unlock credential.
    try:
        client.login(
            json.dumps(
                {
                    "role_id": old["role_id"],
                    "secret_id": private("escrow.json")["provisioner"]["secret_id"],
                }
            ).encode()
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Provisioner SecretID accepted for the unlock role")

elif command == "verify":
    client.wait_unsealed(60)
    unlock = ROOT / "unlock.json"
    unlock.write_bytes(
        run(
            "systemd-creds",
            "decrypt",
            "--name=volume.unlock",
            str(BOOT / "volume-unlock.cred"),
            "-",
        )
    )
    key = client.volume_key("server", "test", UUID, unlock)
    assert len(key) == 32
    for machine, volume, uuid in (
        ("other", "test", UUID),
        ("server", "other", UUID),
        ("server", "test", "22222222-2222-2222-2222-222222222222"),
    ):
        try:
            client.volume_key(machine, volume, uuid, unlock)
        except ValueError:
            pass
        else:
            raise AssertionError("A record outside the volume identity was released")
    unlock.unlink()
