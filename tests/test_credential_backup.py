"""Real age round trips over synthetic credentials; no production secret reads."""

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

from lx_administration.storage import credential_backup as backup


@pytest.fixture
def age(tmp_path):
    binary = shutil.which("age")
    if binary is None:
        pytest.fail(
            "Run in the Devenv shell: real age is required for credential backup tests"
        )
    identity = tmp_path / "identity"
    subprocess.run(["age-keygen", "-o", str(identity)], check=True, capture_output=True)
    recipient = subprocess.check_output(
        ["age-keygen", "-y", str(identity)], text=True
    ).strip()
    return identity, recipient


@pytest.fixture
def environment(tmp_path, monkeypatch, age):
    live = tmp_path / "live"
    live.mkdir()
    credential = live / "admin.hash"
    credential.write_bytes(b"synthetic-sensitive-credential")
    credential.chmod(0o600)
    external = tmp_path / "external"
    external.mkdir(mode=0o700)
    archive = external / "backup.tar.age"
    state = tmp_path / "state"
    plan = {
        "plan_id": "a" * 64,
        "source": {"revision": "b" * 40},
        "spec": {"host": "gc-09", "disks": [{"serial": "system"}]},
        "config": {
            "secret_contract": {"items": [], "vault_server": False, "openbao": False}
        },
    }
    extra = {"accounts": {}, "account_sources": {}}
    monkeypatch.setattr(backup.os, "geteuid", lambda: 0)
    monkeypatch.setattr(backup.resource, "setrlimit", lambda *a: None)
    monkeypatch.setattr(backup, "_require_protected_swap", lambda: None)
    monkeypatch.setattr(backup, "read_plan", lambda *a: plan)
    monkeypatch.setattr(backup, "verify_source", lambda *a: None)
    monkeypatch.setattr(backup, "extra_contract", lambda *a: extra)
    monkeypatch.setattr(backup, "verify_accounts", lambda *a: None)
    monkeypatch.setattr(backup, "selected_roots", lambda *a: ({credential}, set()))
    monkeypatch.setattr(backup.migration, "private_path", lambda *a, **k: None)
    identity, recipient = age
    monkeypatch.setattr(backup.custody, "recipient", lambda *a: recipient)
    monkeypatch.setattr(backup.custody, "independent", lambda *a: None)

    def filesystem(path):
        role = (
            "external"
            if path == external
            else "system"
            if path == credential
            else "key"
        )
        return {
            "uuid": role,
            "fstype": "ext4",
            "fsroot": "/",
            "containers": {},
            "disks": [{"serial": role, "size": 10000}],
        }

    monkeypatch.setattr(backup, "filesystem", filesystem)
    return state, archive, identity, credential, plan, extra


def test_real_encrypted_backup_verifies_without_plaintext_artifacts(
    environment, capsys
):
    state, archive, identity, credential, _, _ = environment
    backup.execute(state, archive, identity, action="backup")
    assert b"synthetic-sensitive-credential" not in archive.read_bytes()
    assert b"admin.hash" not in archive.read_bytes()
    assert archive.stat().st_mode & 0o777 == 0o600
    assert list(archive.parent.iterdir()) == [archive]
    backup.execute(state, archive, identity, action="verify")
    with tarfile.open(
        fileobj=io.BytesIO(
            backup.crypt(["-d", "-i", str(identity)], archive.read_bytes())
        )
    ) as tar:
        member = tar.getmember("files/" + str(credential).lstrip("/"))
        assert tar.extractfile(member).read() == credential.read_bytes()
        assert member.mode == 0o600
    assert "synthetic-sensitive-credential" not in capsys.readouterr().out


def test_preview_never_reads_credentials_or_encrypts(environment, monkeypatch):
    state, archive, _, _, _, _ = environment
    monkeypatch.setattr(
        backup, "collect", lambda *a: pytest.fail("preview read secret")
    )
    monkeypatch.setattr(backup, "crypt", lambda *a: pytest.fail("preview encrypted"))
    backup.execute(state, archive, None, action="preview")
    assert not archive.exists()


@pytest.mark.parametrize(
    "change", ["content", "permissions", "contract", "plan", "drive"]
)
def test_verification_rejects_drift_and_preserves_old_archive(
    environment, monkeypatch, change
):
    state, archive, identity, credential, plan, extra = environment
    backup.execute(state, archive, identity, action="backup")
    original = archive.read_bytes()
    if change == "content":
        credential.write_bytes(b"rotated-synthetic-value")
    elif change == "permissions":
        credential.chmod(0o400)
    elif change == "contract":
        extra["account_sources"] = {"/new/path": "/new/source"}
    elif change == "plan":
        plan["plan_id"] = "c" * 64
    else:
        old = backup.filesystem
        monkeypatch.setattr(
            backup, "filesystem", lambda p: old(p) | {"uuid": "replacement"}
        )
    with pytest.raises(ValueError, match="Backup no longer"):
        backup.execute(state, archive, identity, action="verify")
    assert archive.read_bytes() == original


def test_existing_backup_is_never_overwritten(environment):
    state, archive, identity, _, _, _ = environment
    archive.write_bytes(b"retained-original")
    with pytest.raises(ValueError, match="already exists"):
        backup.execute(state, archive, identity, action="backup")
    assert archive.read_bytes() == b"retained-original"


def test_wrong_identity_and_tamper_fail_authentication(environment, tmp_path):
    state, archive, identity, _, _, _ = environment
    backup.execute(state, archive, identity, action="backup")
    wrong = tmp_path / "wrong-key"
    subprocess.run(["age-keygen", "-o", str(wrong)], check=True, capture_output=True)
    with pytest.raises(ValueError, match="authentication failed"):
        backup.execute(state, archive, wrong, action="verify")
    data = bytearray(archive.read_bytes())
    data[-1] ^= 1
    archive.write_bytes(data)
    with pytest.raises(ValueError, match="authentication failed"):
        backup.execute(state, archive, identity, action="verify")


def test_selected_disk_destination_rejected_before_reading(environment, monkeypatch):
    state, archive, identity, _, _, _ = environment
    monkeypatch.setattr(
        backup, "filesystem", lambda p: {"disks": [{"serial": "system"}]}
    )
    monkeypatch.setattr(backup, "collect", lambda *a: pytest.fail("unsafe backup read"))
    with pytest.raises(ValueError, match="selected for erasure"):
        backup.execute(state, archive, identity, action="backup")
    assert not archive.exists()


def test_missing_symlink_and_special_sources_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "filesystem", lambda p: {"uuid": "source"})
    path = tmp_path / "key"
    policy = {"max_bytes": 100, "max_files": 3}
    with pytest.raises(ValueError, match="missing or locked"):
        backup.collect({path}, {path}, policy)
    target = tmp_path / "actual"
    target.write_bytes(b"synthetic")
    path.symlink_to(target)
    with pytest.raises(ValueError, match="symlinked"):
        backup.collect({path}, {path}, policy)
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(ValueError, match="regular file"):
        backup.collect({path}, {path}, policy)


def test_concurrent_rotation_prevents_publication(environment, monkeypatch):
    state, archive, identity, credential, _, _ = environment
    original = backup.crypt

    def rotate(arguments, data):
        result = original(arguments, data)
        credential.write_bytes(b"concurrent-rotation")
        return result

    monkeypatch.setattr(backup, "crypt", rotate)
    with pytest.raises(ValueError, match="Backup no longer"):
        backup.execute(state, archive, identity, action="backup")
    assert not archive.exists()


def test_device_renumbering_keeps_stable_identity(monkeypatch):
    device = ["/dev/sda"]
    monkeypatch.setattr(backup, "filesystem_devices", lambda fs: [device[0] + "1"])

    def run(*args):
        if args[0] == "findmnt":
            return json.dumps(
                {
                    "filesystems": [
                        {
                            "source": device[0] + "1",
                            "uuid": "same-uuid",
                            "fstype": "ext4",
                            "fsroot": "/",
                        }
                    ]
                }
            )
        return json.dumps(
            {
                "blockdevices": [
                    {"name": device[0], "type": "disk", "serial": "stable", "size": 123}
                ]
            }
        )

    monkeypatch.setattr(backup.migration, "run", run)
    before = backup.filesystem(Path("/recovery"))
    device[0] = "/dev/sdb"
    assert backup.filesystem(Path("/recovery")) == before


def test_account_sources_and_boot_copies_are_required(tmp_path, monkeypatch):
    monkeypatch.setattr(backup.preflight, "retained_volume_keys", lambda p: [])
    plan = {
        "config": {
            "secret_contract": {
                "items": [],
                "vault_server": False,
                "openbao": False,
            }
        }
    }
    extra = {
        "accounts": {"admin": "/boot/admin.hash", "client": "/boot/client.hash"},
        "account_sources": {
            "/boot/admin.hash": "/vault/admin_hash",
            "/boot/client.hash": "/vault/SCRT_client_user_password_hash",
        },
        "ssh_keys": ["/etc/ssh/ssh_host_ed25519_key"],
        "vault_paths": ["/vault"],
        "secret_root": "/etc/secrets",
        "admin_home": str(tmp_path),
    }
    required, _ = backup.selected_roots(plan, extra, {"optional_paths": []})
    assert {
        Path(p)
        for p in [
            *extra["account_sources"],
            *extra["account_sources"].values(),
            *extra["ssh_keys"],
        ]
    } <= required
    (tmp_path / ".lxv").mkdir()
    with pytest.raises(ValueError, match="both be available"):
        backup.selected_roots(plan, extra, {"optional_paths": []})


def test_live_account_mismatch_blocks_without_logging_hash(tmp_path, monkeypatch):
    path = tmp_path / "hash"
    path.write_bytes(b"synthetic-hash")
    from lx_administration.storage import operator_migration

    monkeypatch.setattr(operator_migration, "validate_account_hash", lambda b: b)
    monkeypatch.setattr(backup.migration, "run", lambda *a: "admin:different:1:2")
    with pytest.raises(ValueError, match="differs from its boot hash") as error:
        backup.verify_accounts({"accounts": {"admin": str(path)}})
    assert "synthetic-hash" not in str(error.value)
    assert "different" not in str(error.value)


def test_legacy_loop_records_physical_backing_and_path(monkeypatch):
    monkeypatch.setattr(backup, "filesystem_devices", lambda fs: [fs["source"]])

    def run(*args):
        if args[0] == "findmnt":
            inner = args[3] == "/etc/secrets"
            return json.dumps(
                {
                    "filesystems": [
                        {
                            "source": "/dev/mapper/secrets" if inner else "/dev/sda1",
                            "uuid": "inner" if inner else "outer",
                            "fstype": "ext4",
                            "fsroot": "/",
                        }
                    ]
                }
            )
        if args[0] == "losetup":
            return json.dumps(
                {
                    "loopdevices": [
                        {
                            "name": "/dev/loop0",
                            "back-file": "/data/secrets.img",
                        }
                    ]
                }
            )
        row = (
            {"name": "/dev/loop0", "type": "loop"}
            if args[-1] == "/dev/mapper/secrets"
            else {"name": "/dev/sda", "type": "disk", "serial": "physical", "size": 100}
        )
        return json.dumps({"blockdevices": [row]})

    monkeypatch.setattr(backup.migration, "run", run)
    result = backup.filesystem(Path("/etc/secrets"))
    assert result["disks"] == [{"serial": "physical", "size": 100}]
    assert result["containers"]["/data/secrets.img"]["uuid"] == "outer"
