"""Real age verification with disposable identities and mocked physical-media probes."""

import json
import io
from pathlib import Path
import secrets
import shutil
import sys
from types import SimpleNamespace

import pytest

from lx_administration import secret_storage
from lx_administration.storage import recovery_custody as custody
from lx_administration.storage import migration_archive as archive
from lx_administration.storage import provision
from lx_administration.models.vault import secret


@pytest.mark.parametrize("incomplete", [False, True])
def test_custody_disk_separation_uses_all_verified_members(
    tmp_path, monkeypatch, incomplete
):
    filesystem = {"source": "/dev/mapper/first", "fstype": "btrfs"}
    members = ["/dev/block/253:0", "/dev/block/253:1"]
    checked = []

    def verified_members(record):
        assert record == filesystem
        if incomplete:
            raise ValueError("Incomplete Btrfs member evidence")
        return members

    def probe(args):
        if args[0] == "findmnt":
            return json.dumps({"filesystems": [filesystem]}).encode()
        assert args[0] == "lsblk"
        checked.append(args[-1])
        return json.dumps({"blockdevices": [
            {"type": "disk", "name": "/dev/disk" + str(members.index(args[-1]))}
        ]}).encode()

    assert custody.filesystem_devices is secret_storage.filesystem_devices
    monkeypatch.setattr(custody, "filesystem_devices", verified_members)
    monkeypatch.setattr(custody, "run", probe)
    if incomplete:
        with pytest.raises(ValueError, match="Incomplete"):
            custody.storage_disks(tmp_path)
        assert not checked
    else:
        assert custody.storage_disks(tmp_path) == {"/dev/disk0", "/dev/disk1"}
        assert checked == members


@pytest.fixture
def media(tmp_path, monkeypatch):
    if not shutil.which("age") or not shutil.which("age-keygen"):
        pytest.skip("real age tools required")
    controller = tmp_path / "controller"
    custodian = tmp_path / "custodian"
    controller.mkdir(mode=0o700)
    custodian.mkdir(mode=0o700)
    monkeypatch.setattr(custody, "encrypted_storage", lambda *a, **k: None)
    monkeypatch.setattr(secret, "encrypted_storage", lambda *a, **k: None)
    monkeypatch.setattr(
        custody,
        "storage_disks",
        lambda p: {"external"}
        if custodian in p.parents or p == custodian
        else {"controller"},
    )
    first, second = controller / "backup.agekey", custodian / "offline.agekey"
    custody.create_identity(first)
    custody.create_identity(second)
    return controller, custodian, first, second


def test_prepare_is_idempotent_and_independently_decryptable(media):
    _, _, primary, secondary = media
    before = primary.read_bytes(), secondary.read_bytes()
    assert custody.create_identity(primary) is False
    assert custody.create_identity(secondary) is False
    result = custody.verify_pair(primary, secondary)
    assert result["independent_decryption_verified"]
    assert len(set(result["recipients"])) == 2
    assert before == (primary.read_bytes(), secondary.read_bytes())
    assert primary.stat().st_mode & 0o777 == 0o400


def test_same_disk_or_same_identity_is_not_independent(media, monkeypatch):
    _, _, primary, secondary = media
    original = custody.storage_disks
    monkeypatch.setattr(custody, "storage_disks", lambda _: {"same-disk"})
    with pytest.raises(custody.CustodyError, match="shares a physical"):
        custody.verify_pair(primary, secondary)
    monkeypatch.setattr(custody, "storage_disks", original)
    secondary.chmod(0o600)
    secondary.write_bytes(primary.read_bytes())
    with pytest.raises(custody.CustodyError, match="different recovery"):
        custody.verify_pair(primary, secondary)


def test_ssh_or_partial_identity_is_never_replaced(media):
    controller, _, _, _ = media
    existing = controller / "old-key"
    existing.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nsynthetic-test-only\n")
    existing.chmod(0o600)
    before = existing.read_bytes()
    with pytest.raises(custody.CustodyError, match="dedicated native age"):
        custody.create_identity(existing)
    assert existing.read_bytes() == before
    existing.write_text("interrupted-key-generation")
    with pytest.raises(custody.CustodyError):
        custody.create_identity(existing)
    assert existing.read_text() == "interrupted-key-generation"


def test_backup_authenticates_both_independent_recipients(media, tmp_path):
    _, _, primary, secondary = media
    recipients = custody.verify_pair(primary, secondary)["recipients"]
    target = tmp_path / "archive.age"
    result = archive.transfer(
        None,
        ["printf", "synthetic retained backup"],
        target,
        recipients,
        [primary, secondary],
    )
    assert result["authenticated"]
    for identity in (primary, secondary):
        archive.verify_archive(target, identity, result["sha256_compressed_stream"])
    target.write_bytes(target.read_bytes()[:-1])
    for identity in (primary, secondary):
        with pytest.raises(ValueError, match="authentication"):
            archive.verify_archive(target, identity, result["sha256_compressed_stream"])


def test_backup_not_published_if_independent_identity_fails(media, tmp_path):
    controller, _, primary, secondary = media
    wrong = controller / "wrong.agekey"
    custody.create_identity(wrong)
    target = tmp_path / "archive.age"
    recipients = custody.verify_pair(primary, secondary)["recipients"]
    with pytest.raises(ValueError, match="authentication"):
        archive.transfer(
            None, ["printf", "synthetic"], target, recipients, [primary, wrong]
        )
    assert not target.exists()
    assert target.with_suffix(".age.partial").exists()


def vault_record(controller):
    vault = controller / "vault"
    vault.mkdir(mode=0o700)
    key = controller / "vault.key"
    key.write_bytes(secrets.token_hex(32).encode())
    key.chmod(0o600)
    record = {
        "machine_id": "1" * 32,
        "volume": "test-volume",
        "luks_uuid": "12345678-1234-1234-1234-123456789abc",
        "recovery_passphrase": secrets.token_hex(32),
    }
    return vault, key, record


def test_independent_record_survives_loss_of_admin_vault_key(media):
    controller, external, _, custodian_key = media
    vault, vault_key, record = vault_record(controller)
    source = provision.escrow_record(vault, vault_key, record, None)
    original = source.read_bytes()
    destination = external / "record.age"
    result = custody.export_record(source, vault_key, custodian_key, destination)
    assert result["independent_decryption_verified"]
    encrypted = destination.read_bytes()
    custody.export_record(source, vault_key, custodian_key, destination)
    assert destination.read_bytes() == encrypted
    assert source.read_bytes() == original
    vault_key.unlink()
    recovered = custody.run(["age", "-d", "-i", str(custodian_key), str(destination)])
    assert json.loads(recovered) == record
    assert record["recovery_passphrase"].encode() not in encrypted


def test_configured_escrow_automatically_refreshes_independent_verification(media):
    controller, external, _, custodian_key = media
    vault, vault_key, record = vault_record(controller)
    custody.configure_vault(vault, custodian_key, external)
    assert provision.require_independent_custody(vault)
    source = provision.escrow_record(
        vault, vault_key, record, None, independent_required=True
    )
    destination = external / record["machine_id"] / (record["luks_uuid"] + ".age")
    assert (
        json.loads(
            custody.run(["age", "-d", "-i", str(custodian_key), str(destination)])
        )
        == record
    )
    original = source.read_bytes()
    destination.chmod(0o600)
    destination.write_bytes(b"corrupted")
    with pytest.raises(custody.CustodyError):
        provision.escrow_record(
            vault, vault_key, record, None, independent_required=True
        )
    assert source.read_bytes() == original
    assert destination.read_bytes() == b"corrupted"


def test_required_custody_cannot_disappear_between_precheck_and_escrow(media):
    controller, external, _, custodian_key = media
    vault, vault_key, record = vault_record(controller)
    custody.configure_vault(vault, custodian_key, external)
    provision.require_independent_custody(vault)
    (vault / "storage-recovery/custody.json").unlink()
    with pytest.raises(FileNotFoundError):
        provision.escrow_record(
            vault, vault_key, record, None, independent_required=True
        )


def test_missing_custody_keeps_existing_records_usable(media):
    controller, _, _, _ = media
    vault, vault_key, record = vault_record(controller)
    source = provision.escrow_record(vault, vault_key, record, None)
    with pytest.raises(
        provision.ProvisionError, match="Prepare independent age custody"
    ):
        provision.require_independent_custody(vault)
    assert json.loads(secret.decrypt_secret(source, vault_key)) == record


def test_local_archive_needs_both_recipient_checks_before_publication(
    media, tmp_path, monkeypatch
):
    _, _, primary, secondary = media
    recipients = custody.verify_pair(primary, secondary)["recipients"]
    destination = tmp_path / "backup"
    destination.mkdir()
    root = destination / "luxnix-storage-migration/gc-09-reviewed-01"
    root.mkdir(parents=True)
    target = root / "root.btrfs.gz.age"
    item = archive.transfer(None, ["printf", "synthetic"], target, recipients, None)
    receipt_path = root / "receipt.json"
    plan_path = tmp_path / "plan.json"
    mounts = {
        "root": "/",
        "home": "/home",
        "nix": "/nix",
        "persist": "/persist",
        "var-log": "/var/log",
    }
    plan_path.write_text(
        json.dumps(
            {
                "complete": True,
                "host": "gc-09",
                "identifier": "reviewed-01",
                "mounts": {"/": {"uuid": "source"}},
                "snapshots": [
                    {
                        "name": name,
                        "source": source,
                        "snapshot": "/var/lib/luxnix-migration-snapshots/reviewed-01/"
                        + name,
                    }
                    for name, source in mounts.items()
                ],
            }
        )
    )
    root.chmod(0o700)
    receipt = archive.bind_receipt(root, json.loads(plan_path.read_text()), recipients)
    item['source_plan_sha256'] = receipt['source_plan_sha256']
    receipt['components']['root'] = item
    archive.save_receipt(receipt_path, receipt)
    actual_output = archive.subprocess.check_output

    def output(args, **kwargs):
        if args[0] == "findmnt":
            return '{"filesystems":[{"uuid":"backup"}]}'
        if args[0] == "swapon":
            return ""
        return actual_output(args, **kwargs)

    monkeypatch.setattr(archive.subprocess, "check_output", output)
    monkeypatch.setattr(archive.socket, "gethostname", lambda: "gc-09")
    monkeypatch.setattr(archive.os, "umask", lambda *_: None)
    monkeypatch.setattr(archive.resource, "setrlimit", lambda *_: None)
    monkeypatch.setattr(Path, "is_mount", lambda _: True)
    monkeypatch.setattr(
        archive,
        "Path",
        lambda value: plan_path
        if str(value).startswith("/var/lib/luxnix-migration-snapshots/")
        else Path(value),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "archive",
            "--snapshot-id",
            "reviewed-01",
            "--destination",
            str(destination),
            "--destination-uuid",
            "backup",
            "--recipient",
            recipients[0],
            "--custodian-recipient",
            recipients[1],
            "--verify",
            "root",
        ],
    )
    monkeypatch.setattr(
        sys, "stdin", SimpleNamespace(buffer=io.BytesIO(primary.read_bytes()))
    )
    archive.local_main()
    assert not target.exists()
    assert not json.loads(receipt_path.read_text())["components"]["root"][
        "authenticated"
    ]
    monkeypatch.setattr(
        sys, "stdin", SimpleNamespace(buffer=io.BytesIO(secondary.read_bytes()))
    )
    save = archive.save_receipt
    def interrupted_receipt(path, value):
        if path == receipt_path and value['components']['root']['authenticated']:
            raise RuntimeError('power loss after publication')
        return save(path, value)
    monkeypatch.setattr(archive, 'save_receipt', interrupted_receipt)
    with pytest.raises(RuntimeError, match='power loss'):
        archive.local_main()
    assert target.exists()
    assert not json.loads(receipt_path.read_text())['components']['root']['authenticated']
    monkeypatch.setattr(archive, 'save_receipt', save)
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(secondary.read_bytes())))
    archive.local_main()
    assert target.exists()
    assert json.loads(receipt_path.read_text())["components"]["root"]["authenticated"]
