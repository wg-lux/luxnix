"""Backup refusal, authenticated recovery and snapshot failure cleanup contracts."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from lx_administration.storage import migration_backup as backup
from lx_administration.storage import snapshot


def test_snapshot_scope_rejects_another_host_or_path():
    item = {
        "source": "/",
        "name": "root",
        "snapshot": "/var/lib/luxnix-migration-snapshots/reviewed-01/root",
    }
    backup.validate_snapshot("gc-09", "reviewed-01", item)
    for host, identifier, change in [
        ("gc-02", "reviewed-01", {}),
        ("gc-09", "../outside", {}),
        ("gc-09", "reviewed-01", {"snapshot": "/etc/secrets"}),
        ("gc-09", "reviewed-01", {"source": "/data/raid01"}),
    ]:
        with pytest.raises(ValueError):
            backup.validate_snapshot(host, identifier, item | change)


@pytest.mark.skipif(not shutil.which("age-keygen"), reason="age required")
def test_real_age_archive_authentication_and_wrong_digest(tmp_path):
    identity = tmp_path / "identity"
    subprocess.run(["age-keygen", "-o", str(identity)], check=True, capture_output=True)
    recipient = subprocess.check_output(
        ["age-keygen", "-y", str(identity)], text=True
    ).strip()
    data = b"existing synthetic backup content" * 100
    archive = tmp_path / "backup.age"
    archive.write_bytes(
        subprocess.run(
            ["age", "-r", recipient], input=data, capture_output=True, check=True
        ).stdout
    )
    digest = hashlib.sha256(data).hexdigest()
    backup.verify_archive(archive, identity, digest)
    streamed = tmp_path / "streamed.age"
    receipt = backup.transfer(
        None, ["printf", "synthetic-stream"], streamed, recipient, identity
    )
    assert receipt["authenticated"] and not receipt["application_restore_tested"]
    assert not streamed.with_suffix(".age.partial").exists()
    backup.verify_archive(
        streamed, identity, hashlib.sha256(b"synthetic-stream").hexdigest()
    )
    with pytest.raises(ValueError):
        backup.verify_archive(archive, identity, "0" * 64)
    pending = tmp_path / "host-local.age"
    local = backup.transfer(
        None, ["printf", "host-local-synthetic"], pending, recipient, None
    )
    assert not local["authenticated"] and not pending.exists()
    encrypted = pending.with_suffix(".age.unverified")
    fd = os.memfd_create("test-recovery")
    try:
        os.write(fd, identity.read_bytes())
        os.lseek(fd, 0, os.SEEK_SET)
        backup.verify_archive(
            encrypted,
            Path(f"/proc/self/fd/{fd}"),
            local["sha256_compressed_stream"],
            pass_fds=(fd,),
        )
    finally:
        os.close(fd)
    with pytest.raises(ValueError, match="refusing replacement"):
        backup.transfer(None, ["printf", "replacement"], pending, recipient, None)
    archive.write_bytes(archive.read_bytes()[:-1])
    with pytest.raises(ValueError):
        backup.verify_archive(archive, identity, digest)


def test_existing_backup_never_replaced(tmp_path):
    target = tmp_path / "backup.age"
    target.write_bytes(b"existing")
    with pytest.raises(ValueError, match="refusing replacement"):
        backup.transfer(None, [], target, "unused", tmp_path / "identity")
    assert target.read_bytes() == b"existing"


@pytest.fixture
def snapshot_host(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(snapshot, "BASE", tmp_path / "snapshots")
    monkeypatch.setattr(snapshot.socket, "gethostname", lambda: "gc-09")
    calls = []
    state = {
        "postgresql.service": "active",
        "lx-annotate.service": "inactive",
        "nginx.service": "inactive",
    }
    masks = {"nginx.service"}
    frozen = set()
    identities = {}
    failures = {}

    def mount(path, optional=False):
        return {
            "source": "/dev/mapper/root",
            "fstype": "btrfs",
            "uuid": failures.get("mount_uuid", "filesystem"),
            "fsroot": path,
        }

    def subvolume(path):
        path = str(path)
        return identities.get(path, {"uuid": "source-" + path, "parent_uuid": "-"})

    def run(*args, **kwargs):
        calls.append(args)
        if args[:2] == ("systemctl", "list-units"):
            return (
                "\n".join(u + " loaded " + s for u, s in state.items())
                + "\nsshd.service loaded active"
            )
        if args[:2] == ("systemctl", "show"):
            return (
                ("masked" if args[2] in masks else "loaded")
                if "LoadState" in args
                else state[args[2]]
            )
        if args[:2] == ("systemctl", "mask"):
            masks.add(args[-1])
        if args[:2] == ("systemctl", "unmask"):
            masks.discard(args[-1])
        if args[:2] == ("systemctl", "stop"):
            for unit in args[2:]:
                state[unit] = "inactive"
        if args[:2] == ("systemctl", "start"):
            if failures.get("restart"):
                raise RuntimeError("synthetic restart failure")
            state[args[-1]] = "active"
        if args[:2] == ("fsfreeze", "--freeze"):
            frozen.add(args[-1])
        if args[:3] == ("btrfs", "subvolume", "snapshot"):
            if failures.get("snapshot"):
                raise RuntimeError("synthetic snapshot failure")
            if failures.get("signal"):
                snapshot.interrupted(15, None)
            target = Path(args[-1])
            target.mkdir()
            identities[str(target)] = {
                "uuid": "snapshot-" + str(target),
                "parent_uuid": subvolume(args[-2])["uuid"],
            }
        if args[:3] == ("btrfs", "property", "get"):
            return "ro=false" if failures.get("writable") else "ro=true"
        return ""

    def thaw(path):
        calls.append(("thaw", path))
        if failures.get("thaw"):
            raise RuntimeError("synthetic thaw failure")
        frozen.discard(path)

    monkeypatch.setattr(snapshot, "mount_identity", mount)
    monkeypatch.setattr(snapshot, "subvolume", subvolume)
    monkeypatch.setattr(snapshot, "run", run)
    monkeypatch.setattr(snapshot, "thaw", thaw)
    return SimpleNamespace(
        calls=calls,
        state=state,
        masks=masks,
        frozen=frozen,
        identities=identities,
        failures=failures,
        plan=lambda name="reviewed-01": snapshot.BASE / name / "plan.json",
        read=lambda name="reviewed-01": json.loads(
            (snapshot.BASE / name / "plan.json").read_text()
        ),
    )


def test_snapshot_failure_unfreezes_and_restores_only_previous_writers(snapshot_host):
    host = snapshot_host
    host.failures["snapshot"] = True
    with pytest.raises(RuntimeError, match="synthetic snapshot failure"):
        snapshot.snapshot("gc-09", "reviewed-01")
    assert host.frozen == set()
    assert host.state["postgresql.service"] == "active"
    assert host.state["lx-annotate.service"] == "inactive"
    assert host.masks == {"nginx.service"}
    assert all("sshd.service" not in args for args in host.calls)
    assert host.read()["complete"] is False
    assert host.read()["state"] == "recovered"


def test_completed_snapshot_retry_checks_identity_without_stopping_writers(
    snapshot_host,
):
    host = snapshot_host
    first = snapshot.snapshot("gc-09", "reviewed-01")
    assert first["complete"] and first["changed"]
    assert len(first["snapshots"]) == 5
    before = host.plan().read_bytes()
    host.calls.clear()
    repeated = snapshot.snapshot("gc-09", "reviewed-01")
    assert not repeated["changed"]
    assert host.plan().read_bytes() == before
    assert not any(args[0] in {"systemctl", "fsfreeze"} for args in host.calls)
    host.failures["writable"] = True
    with pytest.raises(ValueError, match="not read-only"):
        snapshot.snapshot("gc-09", "reviewed-01")


def test_snapshot_retry_rejects_substituted_snapshot_or_source(snapshot_host):
    host = snapshot_host
    report = snapshot.snapshot("gc-09", "reviewed-01")
    target = report["snapshots"][0]["snapshot"]
    host.identities[target] = {"uuid": "replacement", "parent_uuid": "source-/"}
    with pytest.raises(ValueError, match="identity changed"):
        snapshot.snapshot("gc-09", "reviewed-01")
    host.failures["mount_uuid"] = "another-filesystem"
    with pytest.raises(ValueError, match="Source changed"):
        snapshot.snapshot("gc-09", "reviewed-01", "recover")


def test_thaw_failure_keeps_writers_masked_until_explicit_recovery(snapshot_host):
    host = snapshot_host
    host.failures.update(snapshot=True, thaw=True)
    with pytest.raises(RuntimeError, match="Operator recovery required"):
        snapshot.snapshot("gc-09", "reviewed-01")
    assert host.state["postgresql.service"] == "inactive"
    assert host.masks == {"nginx.service", "postgresql.service", "lx-annotate.service"}
    assert host.read()["state"] == "recovery_required"
    with pytest.raises(ValueError, match="Incomplete run"):
        snapshot.snapshot("gc-09", "reviewed-01")
    with pytest.raises(ValueError, match="Interrupted run"):
        snapshot.snapshot("gc-09", "reviewed-02")
    host.failures.clear()
    assert snapshot.snapshot("gc-09", "reviewed-01", "recover")["changed"]
    assert host.frozen == set() and host.masks == {"nginx.service"}
    assert host.state["postgresql.service"] == "active"
    assert not snapshot.snapshot("gc-09", "reviewed-01", "recover")["changed"]
    with pytest.raises(ValueError, match="new snapshot identifier"):
        snapshot.snapshot("gc-09", "reviewed-01")
    assert snapshot.snapshot("gc-09", "reviewed-02")["complete"]


def test_restart_failure_is_retained_for_explicit_retry(snapshot_host):
    host = snapshot_host
    host.failures["restart"] = True
    with pytest.raises(RuntimeError, match="restart postgresql"):
        snapshot.snapshot("gc-09", "reviewed-01")
    assert host.read()["pending_restart"] == ["postgresql.service"]
    assert host.read()["complete"] is False
    host.failures.clear()
    assert snapshot.snapshot("gc-09", "reviewed-01", "recover")["state"] == "recovered"
    assert host.state["lx-annotate.service"] == "inactive"


def test_catchable_signal_restores_writers_without_claiming_completion(snapshot_host):
    host = snapshot_host
    host.failures["signal"] = True
    with pytest.raises(RuntimeError, match="interrupted by signal"):
        snapshot.snapshot("gc-09", "reviewed-01")
    assert host.frozen == set()
    assert host.state["postgresql.service"] == "active"
    assert host.read()["state"] == "recovered"
    assert not host.read()["complete"]


def test_host_lock_serializes_different_snapshot_identifiers(snapshot_host):
    import sys

    with snapshot.operation("snapshot"):
        # Check the actual cross-process lock directly, independent of host name.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; "
                "from lx_administration.storage import snapshot; "
                "import sys; snapshot.BASE=Path(sys.argv[1]); "
                "snapshot.operation('snapshot').__enter__()",
                str(snapshot.BASE),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "Another snapshot operation is running" in result.stderr


def test_journal_intents_survive_uncatchable_worker_exit(snapshot_host):
    import json
    import sys

    host = snapshot_host
    # Start from a valid journal then model a crash after intent publication but
    # before the operation acknowledges thaw/mask changes. No finally can run.
    snapshot.snapshot("gc-09", "reviewed-01")
    report = host.read()
    report.update(
        state="in_progress",
        complete=False,
        pending_freezes=list(snapshot.INNER),
        pending_masks=["postgresql.service"],
        pending_restart=["postgresql.service"],
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, os, sys, signal; from pathlib import Path; "
            "from lx_administration.storage.snapshot import save; "
            "save(Path(sys.argv[1]), json.loads(sys.argv[2])); "
            "os.kill(os.getpid(), signal.SIGKILL)",
            str(host.plan()),
            json.dumps(report),
        ]
    )
    assert result.returncode == -9
    with pytest.raises(ValueError, match="Interrupted run"):
        snapshot.snapshot("gc-09", "reviewed-02")
    host.state["postgresql.service"] = "inactive"
    host.masks.add("postgresql.service")
    recovered = snapshot.automatic_recovery("gc-09", "reviewed-01")
    assert recovered["state"] == "recovered" and not recovered["complete"]
    assert len(recovered["snapshots"]) == 5
    assert host.state["postgresql.service"] == "active"


def test_automatic_recovery_retries_transient_thaw_without_new_snapshot(
    snapshot_host, monkeypatch
):
    host = snapshot_host
    host.failures.update(snapshot=True, thaw=True)
    with pytest.raises(RuntimeError):
        snapshot.snapshot("gc-09", "reviewed-01")
    sleeps = []

    def retry_delay(seconds):
        sleeps.append(seconds)
        host.failures.clear()

    monkeypatch.setattr(snapshot.time, "sleep", retry_delay)
    host.calls.clear()
    result = snapshot.automatic_recovery("gc-09", "reviewed-01")
    assert result["state"] == "recovered" and not result["complete"]
    assert sleeps == [5]
    assert host.frozen == set()
    assert not any(
        args[:3] == ("btrfs", "subvolume", "snapshot") for args in host.calls
    )


def test_automatic_recovery_is_bounded_and_never_starts_after_bad_thaw(
    snapshot_host, monkeypatch
):
    host = snapshot_host
    host.failures.update(snapshot=True, thaw=True)
    with pytest.raises(RuntimeError):
        snapshot.snapshot("gc-09", "reviewed-01")
    sleeps = []
    monkeypatch.setattr(snapshot.time, "sleep", sleeps.append)
    host.calls.clear()
    with pytest.raises(RuntimeError, match="unfreeze"):
        snapshot.automatic_recovery("gc-09", "reviewed-01")
    assert sleeps == [5, 5]
    assert not any(args[:2] == ("systemctl", "start") for args in host.calls)
    assert host.read()["pending_freezes"]


def test_sealed_openbao_keeps_writers_masked_until_semantic_recovery(
    snapshot_host, monkeypatch
):
    host = snapshot_host
    host.state["openbao-local.service"] = "active"
    monkeypatch.setattr(
        snapshot, "openbao_ready", lambda: (_ for _ in ()).throw(ValueError("sealed"))
    )
    with pytest.raises(RuntimeError, match="unsealed active local OpenBao"):
        snapshot.snapshot("gc-09", "reviewed-01")
    assert host.state["openbao-local.service"] == "active"
    assert host.state["postgresql.service"] == "inactive"
    assert "postgresql.service" in host.masks
    assert "openbao-local.service" in host.read()["pending_restart"]
    monkeypatch.setattr(snapshot, "openbao_ready", lambda: None)
    assert snapshot.automatic_recovery("gc-09", "reviewed-01")["state"] == "recovered"
    assert host.state["postgresql.service"] == "active"


def test_supervision_is_installed_before_snapshot_exec():
    import yaml

    play = yaml.safe_load(
        (
            Path(__file__).resolve().parents[1]
            / "ansible/playbooks/storage-migration-snapshot.yml"
        ).read_text()
    )[0]
    task = next(t for t in play["tasks"] if t["name"].startswith("Run supervised"))
    argv = task["ansible.builtin.command"]["argv"]
    assert argv[0] == "systemd-run"
    cleanup = next(a for a in argv if a.startswith("--property=ExecStopPost="))
    assert cleanup.endswith(" recover-auto")
    assert argv.index(cleanup) < argv.index("/run/current-system/sw/bin/python3")
    assert "--property=KillMode=control-group" in argv
    assert "--property=RuntimeMaxSec=1800" in argv
    assert "--property=TimeoutStopSec=600" in argv


@pytest.mark.parametrize(
    "actual_uuid,requested_uuid", [("wrong-disk", "backup"), ("source", "source")]
)
def test_host_local_backup_rejects_wrong_or_source_filesystem_before_writes(
    tmp_path, monkeypatch, actual_uuid, requested_uuid
):
    import json
    import sys
    from lx_administration.storage import migration_archive as archive

    monkeypatch.setattr(archive.socket, "gethostname", lambda: "gc-09")
    monkeypatch.setattr(archive.os, "umask", lambda mode: 0)
    monkeypatch.setattr(archive.resource, "setrlimit", lambda *args: None)
    monkeypatch.setattr(Path, "is_mount", lambda self: True)
    monkeypatch.setattr(
        archive.subprocess,
        "check_output",
        lambda *a, **k: json.dumps({"filesystems": [{"uuid": actual_uuid}]}),
    )
    plan = {
        "complete": True,
        "host": "gc-09",
        "identifier": "reviewed-01",
        "mounts": {"/": {"uuid": "source"}},
    }
    original_read = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, *a, **k: json.dumps(plan)
        if str(self).startswith("/var/lib/luxnix-migration-snapshots/")
        else original_read(self, *a, **k),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "archive",
            "--snapshot-id",
            "reviewed-01",
            "--destination",
            str(tmp_path),
            "--destination-uuid",
            requested_uuid,
            "--recipient",
            "synthetic-public-recipient",
        ],
    )
    with pytest.raises(SystemExit) as failure:
        archive.local_main()
    assert failure.value.code == 2
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def archive_keys(tmp_path):
    if not shutil.which("age-keygen"):
        pytest.skip("age required")
    from lx_administration.storage import migration_archive as archive

    identities = [tmp_path / "controller.key", tmp_path / "custodian.key"]
    for key in identities:
        subprocess.run(["age-keygen", "-o", str(key)], check=True, capture_output=True)
    recipients = [
        subprocess.check_output(["age-keygen", "-y", str(key)], text=True).strip()
        for key in identities
    ]
    return archive, identities, recipients


@pytest.mark.parametrize("crash_before_publish", [False, True])
def test_completed_transfer_resumes_without_receipt_after_publication_crash(
    tmp_path, monkeypatch, archive_keys, crash_before_publish
):
    archive, keys, recipients = archive_keys
    target = tmp_path / "root.age"
    link = archive.os.link
    if crash_before_publish:
        monkeypatch.setattr(
            archive.os,
            "link",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("power loss")),
        )
        with pytest.raises(RuntimeError, match="power loss"):
            archive.transfer(
                None,
                ["printf", "current snapshot"],
                target,
                recipients,
                keys,
                binding="plan-digest",
            )
        assert not target.exists()
        monkeypatch.setattr(archive.os, "link", link)
    else:
        archive.transfer(
            None,
            ["printf", "current snapshot"],
            target,
            recipients,
            keys,
            binding="plan-digest",
        )
    # No caller receipt was ever saved; completed stream metadata is sufficient.
    recovered = archive.transfer(
        None, ["false"], target, recipients, keys, binding="plan-digest"
    )
    assert recovered["authenticated"]
    assert (
        recovered["sha256_compressed_stream"]
        == hashlib.sha256(b"current snapshot").hexdigest()
    )
    assert not target.with_suffix(".age.partial").exists()
    with pytest.raises(ValueError, match="differs"):
        archive.transfer(
            None, ["false"], target, recipients, keys, binding="other-plan"
        )


def test_host_local_publication_gap_preserves_required_independent_checks(
    tmp_path, archive_keys
):
    archive, keys, recipients = archive_keys
    target = tmp_path / "root.age"
    first = archive.transfer(
        None, ["printf", "current snapshot"], target, recipients, None, binding="plan"
    )
    recovered = archive.transfer(
        None, ["false"], target, recipients, None, binding="plan"
    )
    assert first == recovered and not recovered["authenticated"]
    assert not target.exists()
    for key in keys:
        archive.verify_archive(
            target.with_suffix(".age.unverified"),
            key,
            recovered["sha256_compressed_stream"],
        )


@pytest.mark.parametrize(
    "changed", ["host", "identifier", "snapshot_identity", "mount", "recipients"]
)
def test_receipt_rejects_substitution_before_rewriting_plan(tmp_path, changed):
    import copy
    from lx_administration.storage import migration_archive as archive

    plan = {
        "host": "gc-09",
        "identifier": "reviewed-01",
        "mounts": {"/": {"uuid": "source"}},
        "snapshots": [{"name": "root", "identity": {"uuid": "snapshot"}}],
    }
    recipients = ["controller", "custodian"]
    archive.bind_receipt(tmp_path, plan, recipients)
    original = (tmp_path / "source-plan.json").read_bytes()
    different = copy.deepcopy(plan)
    if changed in {"host", "identifier"}:
        different[changed] = "substituted"
    elif changed == "snapshot_identity":
        different["snapshots"][0]["identity"]["uuid"] = "substituted"
    elif changed == "mount":
        different["mounts"]["/"]["uuid"] = "substituted"
    else:
        recipients = ["controller", "replacement"]
    with pytest.raises(ValueError, match="differs"):
        archive.bind_receipt(tmp_path, different, recipients)
    assert (tmp_path / "source-plan.json").read_bytes() == original


@pytest.mark.parametrize("name", [".lock", "receipt.json", "receipt.pending"])
def test_external_metadata_symlinks_never_read_or_overwrite_destination(tmp_path, name):
    from lx_administration.storage import migration_archive as archive

    victim = tmp_path / "outside"
    victim.write_text("preserve me")
    victim.chmod(0o600)
    root = tmp_path / "backup"
    root.mkdir(mode=0o700)
    (root / name).symlink_to(victim)
    with pytest.raises(OSError):
        if name == ".lock":
            archive.private_open(root / name, os.O_RDWR | os.O_CREAT)
        else:
            archive.save_receipt(root / "receipt.json", {"complete": False})
    assert victim.read_text() == "preserve me"


@pytest.mark.parametrize("unsafe", ["permissions", "directory", "hardlink", "owner"])
def test_metadata_reuse_checks_opened_file_type_owner_and_permissions(
    tmp_path, monkeypatch, unsafe
):
    from lx_administration.storage import migration_archive as archive

    path = tmp_path / ".lock"
    if unsafe == "directory":
        path.mkdir()
    else:
        path.write_text("{}")
        path.chmod(0o644 if unsafe == "permissions" else 0o600)
        if unsafe == "hardlink":
            os.link(path, tmp_path / "alias")
        if unsafe == "owner":
            actual_uid = os.geteuid()
            monkeypatch.setattr(archive.os, "geteuid", lambda: actual_uid + 1)
    with pytest.raises((ValueError, IsADirectoryError)):
        archive.private_open(path)


def test_orphan_adoption_requires_current_source_and_both_recovery_identities(
    tmp_path, archive_keys
):
    archive, keys, recipients = archive_keys
    target = tmp_path / "orphan.age"
    target.write_bytes(
        subprocess.run(
            ["age", *[arg for r in recipients for arg in ["-r", r]]],
            input=b"current snapshot",
            capture_output=True,
            check=True,
        ).stdout
    )
    before = target.read_bytes()
    with pytest.raises(ValueError, match="checksum"):
        archive.recover_existing(
            None, ["printf", "another snapshot"], target, recipients, keys, "plan"
        )
    assert not target.with_suffix(".age.json").exists()
    archive.recover_existing(
        None, ["printf", "current snapshot"], target, recipients, keys, "plan"
    )
    result = archive.transfer(None, ["false"], target, recipients, keys, binding="plan")
    assert result["authenticated"] and target.read_bytes() == before


@pytest.mark.parametrize("verify", [False, True])
def test_host_local_rejects_same_recipient_before_binding(
    tmp_path, monkeypatch, verify
):
    import json
    import sys
    from lx_administration.storage import migration_archive as archive

    monkeypatch.setattr(archive.socket, "gethostname", lambda: "gc-09")
    monkeypatch.setattr(archive.resource, "setrlimit", lambda *a: None)
    monkeypatch.setattr(Path, "is_mount", lambda _: True)
    monkeypatch.setattr(
        archive.subprocess,
        "check_output",
        lambda *a, **k: '{"filesystems":[{"uuid":"backup"}]}',
    )
    plan = {
        "complete": True,
        "host": "gc-09",
        "identifier": "reviewed-01",
        "mounts": {"/": {"uuid": "source"}},
        "snapshots": [
            {
                "name": n,
                "source": p,
                "snapshot": "/var/lib/luxnix-migration-snapshots/reviewed-01/" + n,
            }
            for n, p in archive.snapshot_sources("gc-09").items()
        ],
    }
    original_read = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, *a, **k: json.dumps(plan)
        if str(self).startswith("/var/lib/luxnix-migration-snapshots/")
        else original_read(self, *a, **k),
    )
    recipient = "age1" + "a" * 58
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "archive",
            "--snapshot-id",
            "reviewed-01",
            "--destination",
            str(tmp_path),
            "--destination-uuid",
            "backup",
            "--recipient",
            recipient,
            "--custodian-recipient",
            recipient,
        ]
        + (["--verify", "root", "--recover-existing"] if verify else []),
    )
    with pytest.raises(SystemExit) as failure:
        archive.local_main()
    assert failure.value.code == 2
    assert not list(tmp_path.rglob("receipt*"))


@pytest.mark.parametrize("created", [False, True])
def test_snapshot_creation_crash_reconciles_durable_pending_intent(
    snapshot_host, monkeypatch, created
):
    host = snapshot_host
    original_run = snapshot.run

    def interrupted_creation(*args, **kwargs):
        if args[:3] == ("btrfs", "subvolume", "snapshot"):
            if created:
                original_run(*args, **kwargs)
            os._exit(91)
        return original_run(*args, **kwargs)

    monkeypatch.setattr(snapshot, "run", interrupted_creation)
    # Fork only the synthetic Btrfs/systemd fixture. The child exits before any
    # finally block, leaving the actual journal and created directory on disk.
    pid = os.fork()
    if pid == 0:
        try:
            snapshot.snapshot("gc-09", "reviewed-01")
        finally:
            os._exit(92)
    assert os.waitpid(pid, 0)[1] == 91 << 8
    report = host.read()
    pending = report["pending_snapshot"]
    target = Path(pending["snapshot"])
    assert target.exists() == created
    assert report["snapshots"] == [] and report["state"] == "in_progress"
    host.state["postgresql.service"] = "inactive"
    host.masks.update(report["pending_masks"])
    host.frozen.update(report["pending_freezes"])
    if created:
        host.identities[str(target)] = {
            "uuid": "created-before-crash",
            "parent_uuid": "source-/",
        }
    monkeypatch.setattr(snapshot, "run", original_run)
    host.calls.clear()
    recovered = snapshot.automatic_recovery("gc-09", "reviewed-01")
    assert recovered["state"] == "recovered" and not recovered["complete"]
    assert "pending_snapshot" not in host.read()
    assert host.frozen == set() and host.state["postgresql.service"] == "active"
    assert not any(
        args[:3] == ("btrfs", "subvolume", "snapshot") for args in host.calls
    )
    assert len(recovered["snapshots"]) == int(created)
    if created:
        assert recovered["snapshots"][0]["identity"]["uuid"] == "created-before-crash"
        host.identities[str(target)]["uuid"] = "replacement"
        with pytest.raises(ValueError, match="identity changed"):
            snapshot.snapshot("gc-09", "reviewed-01", "recover")


@pytest.mark.parametrize(
    "unsafe", ["parent_uuid", "writable", "symlink", "not_subvolume"]
)
def test_pending_snapshot_requires_review_before_writer_restart(
    snapshot_host, monkeypatch, unsafe
):
    host = snapshot_host
    snapshot.snapshot("gc-09", "reviewed-01")
    report = host.read()
    candidate = report["snapshots"].pop()
    report["pending_snapshot"] = {k: v for k, v in candidate.items() if k != "identity"}
    report.update(
        state="recovered",
        complete=False,
        pending_masks=["postgresql.service"],
        pending_restart=["postgresql.service"],
        pending_freezes=list(snapshot.INNER),
    )
    target = Path(candidate["snapshot"])
    if unsafe == "parent_uuid":
        host.identities[str(target)]["parent_uuid"] = "another-source"
    elif unsafe == "writable":
        host.failures["writable"] = True
    elif unsafe == "symlink":
        target.rmdir()
        target.symlink_to(target.parent / "root", target_is_directory=True)
    else:
        original = snapshot.subvolume
        monkeypatch.setattr(
            snapshot,
            "subvolume",
            lambda path: (_ for _ in ()).throw(ValueError("not a subvolume"))
            if Path(path) == target
            else original(path),
        )
    snapshot.save(host.plan(), report)
    host.state["postgresql.service"] = "inactive"
    host.masks.add("postgresql.service")
    host.frozen.update(snapshot.INNER)
    host.calls.clear()
    with pytest.raises(ValueError, match="Interrupted run"):
        snapshot.snapshot("gc-09", "reviewed-02")
    with pytest.raises(RuntimeError, match="reconcile retained snapshots"):
        snapshot.snapshot("gc-09", "reviewed-01", "recover")
    retained = host.read()
    assert retained["state"] == "recovery_required" and retained["pending_snapshot"]
    assert target.exists() or target.is_symlink()
    assert host.frozen == set()  # An invalid pending artifact never strands freezes.
    assert host.state["postgresql.service"] == "inactive"
    assert not any(args[:2] == ("systemctl", "start") for args in host.calls)


@pytest.mark.parametrize(
    "field",
    [
        "recovery_identity",
        "custodian_identity",
        "custody",
        "tool_sha256",
        "source_revision",
        "component",
    ],
)
def test_receipt_rejects_provenance_or_component_substitution_without_metadata_writes(
    tmp_path, field
):
    import copy
    from lx_administration.storage import migration_archive as archive

    plan = {
        "host": "gc-09",
        "identifier": "reviewed-01",
        "snapshots": [
            {"name": "root", "identity": {"uuid": "snapshot", "parent_uuid": "source"}}
        ],
    }
    selected = {
        "recovery_identity": "/controller/key",
        "custodian_identity": "/custodian/key",
        "custody": {
            "schema_version": 1,
            "recipients": ["one", "two"],
            "independent_decryption_verified": True,
            "verified_at": 10,
        },
        "tool_sha256": "current-tool",
        "source_revision": "current-revision",
    }
    receipt = archive.bind_receipt(tmp_path, plan, ["one", "two"], selected)
    receipt["components"]["root"] = {
        "source_plan_sha256": receipt["source_plan_sha256"]
    }
    if field == "component":
        receipt["components"]["root"]["source_plan_sha256"] = "another-plan"
    else:
        receipt[field] = (
            {"recipients": ["one", "unselected"]}
            if field == "custody"
            else "substituted"
        )
    archive.save_receipt(tmp_path / "receipt.json", receipt)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    current = copy.deepcopy(selected)
    current["custody"]["verified_at"] = 20
    with pytest.raises(ValueError, match="differs"):
        archive.bind_receipt(tmp_path, plan, ["one", "two"], current)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_custody_fresh_verification_preserves_original_receipt(tmp_path):
    from lx_administration.storage import migration_archive as archive

    plan = {"host": "gc-09", "identifier": "reviewed-01", "snapshots": []}
    selected = {
        "custody": {
            "recipients": ["one", "two"],
            "verified_at": 10,
            "independent_decryption_verified": True,
        }
    }
    first = archive.bind_receipt(tmp_path, plan, ["one", "two"], selected)
    repeated = archive.bind_receipt(
        tmp_path,
        plan,
        ["two", "one"],
        {"custody": selected["custody"] | {"verified_at": 20}},
    )
    assert first == repeated and repeated["custody"]["verified_at"] == 10


def test_copied_self_consistent_archive_and_receipt_cannot_be_relabelled(
    tmp_path, archive_keys
):
    import copy

    archive, keys, recipients = archive_keys
    original = tmp_path / "original"
    original.mkdir(mode=0o700)
    plan = {
        "host": "gc-09",
        "identifier": "reviewed-01",
        "snapshots": [
            {
                "name": "root",
                "identity": {"uuid": "snapshot-one", "parent_uuid": "source"},
            }
        ],
    }
    receipt = archive.bind_receipt(original, plan, recipients)
    target = original / "root.age"
    receipt["components"]["root"] = archive.transfer(
        None,
        ["printf", "valid old snapshot"],
        target,
        recipients,
        keys,
        binding=receipt["source_plan_sha256"],
    )
    receipt["complete"] = True
    archive.save_receipt(original / "receipt.json", receipt)
    copied = tmp_path / "copied"
    shutil.copytree(original, copied)
    before = {p.name: p.read_bytes() for p in copied.iterdir()}
    current = copy.deepcopy(plan)
    current["snapshots"][0]["identity"]["uuid"] = "snapshot-two"
    # Original archive and checksums are valid for both identities, but none of
    # that is evidence of this newly selected snapshot.
    for key in keys:
        archive.verify_archive(
            copied / "root.age",
            key,
            receipt["components"]["root"]["sha256_compressed_stream"],
        )
    with pytest.raises(ValueError, match="differs"):
        archive.bind_receipt(copied, current, recipients)
    assert {p.name: p.read_bytes() for p in copied.iterdir()} == before


def test_snapshot_identity_probe_failure_keeps_creation_intent_for_recovery(
    snapshot_host, monkeypatch
):
    host = snapshot_host
    original = snapshot.subvolume
    monkeypatch.setattr(
        snapshot,
        "subvolume",
        lambda path: (_ for _ in ()).throw(ValueError("metadata unavailable"))
        if Path(path).is_relative_to(snapshot.BASE)
        else original(path),
    )
    with pytest.raises(RuntimeError, match="reconcile retained snapshots"):
        snapshot.snapshot("gc-09", "reviewed-01")
    pending = host.read()["pending_snapshot"]
    assert Path(pending["snapshot"]).is_dir()
    assert host.read()["snapshots"] == []
    assert host.frozen == set() and host.state["postgresql.service"] == "inactive"
    monkeypatch.setattr(snapshot, "subvolume", original)
    recovered = snapshot.snapshot("gc-09", "reviewed-01", "recover")
    assert recovered["state"] == "recovered" and len(recovered["snapshots"]) == 1
    assert "pending_snapshot" not in host.read()
    assert host.state["postgresql.service"] == "active"
