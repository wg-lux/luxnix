"""Root setup never turns an uncertain disk write into an automatic retry."""

import json
from pathlib import Path
import subprocess

import pytest
from pydantic import ValidationError

from lx_administration.storage import boot_migration as migration
from lx_administration.storage import boot_setup as setup
from tests import test_boot_migration as migration_tests

state = migration_tests.state
install_environment = migration_tests.install_environment
seed_assessment = migration_tests.seed_assessment


@pytest.fixture
def environment(install_environment, monkeypatch):
    root, plan, progress = install_environment
    mounts = {
        "/": {"uuid": "root-uuid", "fsroot": "/", "source": "/dev/mapper/cryptroot"},
        "/boot": {"uuid": "efi-uuid", "fsroot": "/", "source": "/dev/test1"},
    }
    disk = setup.BlockDevice(
        path="/dev/test",
        type="disk",
        serial="test-serial",
        size=1000,
        fstype=None,
        uuid=None,
        mountpoints=[],
    )
    calls = []
    monkeypatch.setattr(setup, "verify_provision_namespace", lambda *a: None)
    monkeypatch.setattr(setup, "provisioner", lambda p: Path("/pinned/disko"))
    monkeypatch.setattr(setup, "snapshot_disks", lambda p: [disk])
    monkeypatch.setattr(migration, "verify_unmounted_targets", lambda p: None)
    monkeypatch.setattr(migration, "verify_layout", lambda *a: mounts)
    monkeypatch.setattr(migration, "probe_disks", lambda *a: {1})
    monkeypatch.setattr(setup, "confirmation", lambda *a, **k: calls.append("confirm"))

    def run(path, lock):
        # The intent and original metadata must be readable before execution.
        journal = setup.load_journal(root, plan)
        assert journal.phase == setup.Phase.RUNNING
        assert journal.before == [disk]
        assert lock >= 0
        calls.append("format")

    monkeypatch.setattr(setup, "run_provisioner", run)
    setup.prepare(root)
    return root, plan, progress, calls, mounts


def test_preview_never_prompts_formats_or_changes_journal(environment):
    root, _, _, calls, _ = environment
    before = (root / "provision.json").read_bytes()
    setup.provision(root)
    assert calls == []
    assert (root / "provision.json").read_bytes() == before


def test_completed_provision_is_idempotent_and_prepare_preserves_it(environment):
    root, plan, _, calls, mounts = environment
    setup.provision(root, apply=True)
    assert calls == ["confirm", "format"]
    record = setup.load_journal(root, plan)
    assert record.phase == setup.Phase.COMPLETE
    assert record.model_dump(mode="json")["mounts"] == mounts
    before = (root / "provision.json").read_bytes()
    setup.prepare(root)
    setup.provision(root, apply=True)
    assert calls == ["confirm", "format"]
    assert (root / "provision.json").read_bytes() == before


@pytest.mark.parametrize("failure", [RuntimeError("failed"), KeyboardInterrupt()])
def test_failed_or_interrupted_format_cannot_repeat(environment, monkeypatch, failure):
    root, plan, _, calls, _ = environment

    def fail(*args):
        calls.append("uncertain write")
        raise failure

    monkeypatch.setattr(setup, "run_provisioner", fail)
    with pytest.raises(type(failure)):
        setup.provision(root, apply=True)
    assert setup.load_journal(root, plan).phase == setup.Phase.INTERRUPTED
    with pytest.raises(migration.MigrationError, match="Never retry"):
        setup.provision(root, apply=True)
    assert calls == ["confirm", "uncertain write"]


def test_running_journal_after_process_death_is_not_retried(environment):
    root, plan, _, calls, _ = environment
    record = setup.Journal(
        plan_id=plan["plan_id"],
        phase=setup.Phase.RUNNING,
        before=setup.snapshot_disks(plan),
    )
    setup.save_journal(root, record)
    with pytest.raises(migration.MigrationError, match="Never retry"):
        setup.provision(root, apply=True)
    assert calls == []
    assert setup.next_step(root).action == setup.Action.RECOVER


def test_recovery_accepts_existing_layout_without_formatting(environment):
    root, plan, _, calls, _ = environment
    setup.save_journal(
        root,
        setup.Journal(
            plan_id=plan["plan_id"],
            phase=setup.Phase.INTERRUPTED,
            before=setup.snapshot_disks(plan),
        ),
    )
    setup.provision(root, apply=True, recover_by="named administrator")
    assert calls == ["confirm"]
    assert setup.load_journal(root, plan).recovered_by == "named administrator"
    setup.provision(root, apply=True)
    assert calls == ["confirm"]


def test_recovery_refuses_partial_layout(environment, monkeypatch):
    root, plan, _, calls, _ = environment
    setup.save_journal(
        root,
        setup.Journal(
            plan_id=plan["plan_id"],
            phase=setup.Phase.INTERRUPTED,
            before=setup.snapshot_disks(plan),
        ),
    )

    def partial(*args):
        raise migration.MigrationError("incomplete root")

    monkeypatch.setattr(migration, "verify_layout", partial)
    with pytest.raises(migration.MigrationError, match="incomplete root"):
        setup.provision(root, apply=True, recover_by="administrator")
    assert calls == []
    assert setup.load_journal(root, plan).phase == setup.Phase.INTERRUPTED


def test_cancellation_leaves_plan_unattempted(environment, monkeypatch):
    root, plan, _, calls, _ = environment

    def cancel(*a, **k):
        raise migration.MigrationError("cancelled")

    monkeypatch.setattr(setup, "confirmation", cancel)
    with pytest.raises(migration.MigrationError, match="cancelled"):
        setup.provision(root, apply=True)
    assert calls == []
    assert setup.load_journal(root, plan).phase == setup.Phase.PLANNED


@pytest.mark.parametrize(
    "gate", ["check_gates", "verify_independent_state", "verify_unmounted_targets"]
)
def test_unsafe_precondition_never_reaches_confirmation(environment, monkeypatch, gate):
    root, plan, _, calls, _ = environment

    def unsafe(*args):
        raise migration.MigrationError("unsafe")

    monkeypatch.setattr(migration, gate, unsafe)
    with pytest.raises(migration.MigrationError, match="unsafe"):
        setup.provision(root, apply=True)
    assert calls == []
    assert setup.load_journal(root, plan).phase == setup.Phase.PLANNED


def test_changed_disk_after_confirmation_stops_before_intent(environment, monkeypatch):
    root, plan, _, calls, _ = environment
    before = setup.snapshot_disks(plan)
    monkeypatch.setattr(setup, "snapshot_disks", lambda p: [] if calls else before)
    with pytest.raises(migration.MigrationError, match="changed during approval"):
        setup.provision(root, apply=True)
    assert calls == ["confirm"]
    assert setup.load_journal(root, plan).phase == setup.Phase.PLANNED


def test_intent_publication_failure_prevents_disk_write(environment, monkeypatch):
    root, _, _, calls, _ = environment

    def fail(*args, **kwargs):
        raise OSError("state disk full")

    monkeypatch.setattr(setup, "atomic_write_file", fail)
    with pytest.raises(OSError, match="full"):
        setup.provision(root, apply=True)
    assert calls == ["confirm"]


@pytest.mark.parametrize(
    "field,value", [("phase", "unknown"), ("plan_id", "b" * 64), ("extra", True)]
)
def test_corrupt_journal_fails_closed(environment, field, value):
    root, plan, _, _, _ = environment
    record = json.loads((root / "provision.json").read_text())
    record[field] = value
    (root / "provision.json").write_text(json.dumps(record))
    with pytest.raises((ValidationError, migration.MigrationError)):
        setup.load_journal(root, plan)


def test_completed_schema_requires_real_mount_evidence():
    with pytest.raises(ValidationError):
        setup.Journal(plan_id="a" * 64, phase=setup.Phase.COMPLETE)


def test_next_requires_actual_recovery_evidence(environment):
    root, _, _, calls, _ = environment
    step = setup.advance(root)
    assert step.action == setup.Action.ASSESS
    assert "console_boot_tested" in step.required_checks
    with pytest.raises(migration.MigrationError, match="Record actual recovery"):
        setup.advance(root, apply=True)
    assert calls == []


def test_sequenced_access_and_install_preserve_recorded_mount_binding(
    environment, tmp_path, monkeypatch
):
    root, plan, progress, calls, mounts = environment
    for stage in migration.stage_order(plan)[:-1]:
        seed_assessment((root, plan, progress), stage, tmp_path)
    monkeypatch.setattr(migration, "verify_readiness", lambda *a, **k: None)
    assert setup.next_step(root).action == setup.Action.PROVISION
    setup.advance(root, apply=True)
    assert setup.next_step(root).action == setup.Action.PREPARE_ACCESS

    def access(state, *, expected_mounts):
        assert expected_mounts == mounts
        calls.append("access")

    monkeypatch.setattr(migration, "prepare_access", access)
    setup.advance(root, apply=True)
    assert calls[-1] == "access"
    # Automation never claims that credential/restore/recovery checks were done.
    assert "prepared" not in migration.load_progress(root, plan)["attestations"]
    seed_assessment((root, plan, progress), "prepared", tmp_path)

    def install(state, *, expected_mounts):
        assert expected_mounts == mounts
        calls.append("install")

    monkeypatch.setattr(migration, "install", install)
    setup.advance(root, apply=True)
    assert calls[-1] == "install"


def test_prepared_mount_substitution_refused_by_native_install(
    install_environment, monkeypatch
):
    root, _, _ = install_environment
    with pytest.raises(migration.MigrationError, match="identities changed"):
        migration.install(root, expected_mounts={"/": {"uuid": "different"}})


def test_piped_confirmation_is_never_approval(state):
    _, plan, _ = state
    code = (
        "from lx_administration.storage.boot_setup import confirmation; "
        f"confirmation({plan!r})"
    )
    result = subprocess.run(
        [str(Path(".venv/bin/python").absolute()), "-c", code],
        input="ERASE gc-09\n",
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "interactive installer terminal" in result.stderr


def test_real_tty_requires_exact_host_plan_and_serial(state):
    import pexpect

    _, plan, _ = state
    code = (
        "from lx_administration.storage.boot_setup import confirmation; "
        f"confirmation({plan!r}); print('APPROVED')"
    )
    phrase = f"ERASE gc-09 {plan['plan_id'][:12]} test-serial"
    for answer, approved in [("yes", False), (phrase, True)]:
        child = pexpect.spawn(
            str(Path(".venv/bin/python").absolute()),
            ["-c", code],
            encoding="utf-8",
            timeout=15,
        )
        child.expect_exact("> ")
        child.sendline(answer)
        child.expect(pexpect.EOF)
        assert ("APPROVED" in child.before) is approved
        child.close()
        assert child.exitstatus == (0 if approved else 1)


def test_provisioner_requires_pinned_store_program(state):
    _, plan, _ = state
    with pytest.raises(migration.MigrationError, match="pinned Disko"):
        setup.provisioner(plan)
    plan["config"]["provisioner"] = "/bin/true"
    with pytest.raises(migration.MigrationError, match="pinned Disko"):
        setup.provisioner(plan)


def test_observe_records_only_configured_disk_and_real_hardware(
    state, monkeypatch, tmp_path
):
    _, plan, _ = state
    hardware = tmp_path / "hardware-uuid"
    hardware.write_text(plan["spec"]["hardware_uuid"])
    monkeypatch.setattr(migration, "DMI_UUID", hardware)
    monkeypatch.setattr(migration, "source_identity", lambda p: plan["source"])
    path = plan["spec"]["disks"][0]["path"]
    monkeypatch.setattr(migration, "evaluate", lambda *a: {"disks": {"root": path}})
    calls = []

    def run(*args):
        calls.append(args)
        return json.dumps(
            {
                "blockdevices": [
                    {
                        "path": "/dev/test",
                        "type": "disk",
                        "size": 1000,
                        "serial": "test-serial",
                        "fstype": None,
                        "uuid": None,
                        "mountpoints": [],
                    }
                ]
            }
        )

    monkeypatch.setattr(migration, "run", run)
    spec = setup.observe(
        Path(plan["spec"]["checkout"]), "gc-09", "disposable", "discard-approved"
    )
    assert spec["disks"] == plan["spec"]["disks"]
    assert spec["hardware_uuid"] == hardware.read_text()
    assert calls[0][-1] == path
    assert "--nodeps" in calls[0]
    assert setup.snapshot_disks(plan)[0].serial == "test-serial"
    assert "--nodeps" not in calls[-1]
    with pytest.raises(migration.MigrationError):
        setup.observe(
            Path(plan["spec"]["checkout"]), "gc-09", "disposable", "new-disks"
        )
    with pytest.raises(migration.MigrationError, match="host name"):
        setup.observe(Path("/release"), 'gc-09"; abort', "fresh", "new-disks")


@pytest.mark.parametrize("mount", ["/mnt", "/mnt/recovery"])
def test_provision_refuses_to_unmount_other_storage(tmp_path, monkeypatch, mount):
    monkeypatch.setattr(
        migration, "run", lambda *a: json.dumps({"filesystems": [{"target": mount}]})
    )
    with pytest.raises(migration.MigrationError, match="Unmount /mnt"):
        setup.verify_provision_namespace(tmp_path / "absent-script", {1})


def test_provision_rejects_global_partition_and_mapper_collisions(
    tmp_path, monkeypatch
):
    script = tmp_path / "disko"
    script.write_text(
        "cryptsetup /dev/disk/by-partlabel/nixos_root /dev/mapper/cryptswap"
    )
    monkeypatch.setattr(
        migration, "run", lambda *a: json.dumps({"filesystems": [{"target": "/"}]})
    )
    monkeypatch.setattr(Path, "exists", lambda p: True)
    monkeypatch.setattr(migration, "device_disks", lambda p: {2})
    with pytest.raises(migration.MigrationError, match="unselected disk"):
        setup.verify_provision_namespace(script, {1})
    monkeypatch.setattr(migration, "device_disks", lambda p: {1})
    setup.verify_provision_namespace(script, {1})


def test_formatter_does_not_inherit_test_password_or_shell_injection(monkeypatch):
    monkeypatch.setenv("IN_DISKO_TEST", "1")
    monkeypatch.setenv("BASH_ENV", "/untrusted")
    monkeypatch.setenv("password", "never-inherit")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)))
    setup.run_provisioner(Path("/pinned/disko"), 42)
    args, kwargs = calls[0]
    assert args == (["/pinned/disko"],)
    assert kwargs["pass_fds"] == (42,)
    assert kwargs["check"] is True
    assert set(kwargs["env"]) == {"PATH", "HOME", "LANG", "TERM"}


@pytest.mark.parametrize(
    "target, digest_ok",
    [
        ("/nix/store/" + "b" * 32 + "-disko/bin/disko", True),
        ("/nix/store/" + "b" * 32 + "-disko/bin/disko", False),
        ("/outside/disko", True),
    ],
)
def test_pinned_store_symlink_is_verified_not_blindly_followed(
    state, monkeypatch, target, digest_ok
):
    from types import SimpleNamespace
    import stat

    _, plan, _ = state
    path = "/nix/store/" + "a" * 32 + "-disko"
    plan["config"].update(provisioner=path, provisioner_sha256="expected")
    monkeypatch.setattr(Path, "resolve", lambda p, **k: Path(target))
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda p: SimpleNamespace(
            st_uid=0,
            st_mode=(stat.S_IFLNK | 0o777)
            if str(p) == path
            else (stat.S_IFREG | 0o555),
        ),
    )
    monkeypatch.setattr(
        migration, "file_digest", lambda p: "expected" if digest_ok else "changed"
    )
    if digest_ok and target.startswith("/nix/store/"):
        assert setup.provisioner(plan) == Path(path)
    else:
        with pytest.raises(migration.MigrationError):
            setup.provisioner(plan)


def test_invalid_transition_preserves_journal(environment):
    root, plan, _, _, _ = environment
    before = setup.journal_path(root).read_bytes()
    with pytest.raises(ValidationError):
        setup.save_journal(
            root, setup.load_journal(root, plan), phase=setup.Phase.COMPLETE
        )
    assert setup.journal_path(root).read_bytes() == before


def test_direct_provision_cli_is_removed(monkeypatch):
    monkeypatch.setattr("sys.argv", ["boot-storage-setup", "provision"])
    with pytest.raises(SystemExit) as error:
        setup.main()
    assert error.value.code == 2
