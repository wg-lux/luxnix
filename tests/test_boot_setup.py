"""Root setup admits only in-place encryption and preserves interrupted journals."""

import json
from pathlib import Path
import subprocess

import pytest
from pydantic import ValidationError

from lx_administration.storage import boot_migration as migration
from lx_administration.storage import boot_setup as setup
from tests import test_boot_migration as migration_tests

@pytest.fixture
def state(tmp_path, monkeypatch):
    root, plan, progress = migration_tests.state.__wrapped__(tmp_path, monkeypatch)
    plan["spec"].update(installation="in-place", source_retention="in-place")
    plan["config"]["in_place"] = {
        "root_device": "/dev/test1", "swap_partitions": [], "containers": [],
    }
    plan["plan_id"] = migration.digest(
        {k: v for k, v in plan.items() if k != "plan_id"}
    )
    progress["plan_id"] = plan["plan_id"]
    migration.atomic_json(root / "plan.json", plan)
    migration.atomic_json(root / "progress.json", progress)
    return root, plan, progress

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
    from lx_administration.storage import in_place, boot_password
    monkeypatch.setattr(migration, "device_disks", lambda *a: {1})
    monkeypatch.setattr(in_place, "root_state", lambda *a: in_place.PLAINTEXT)
    monkeypatch.setattr(boot_password, "secret", lambda *a: b"test passphrase 1234")
    monkeypatch.setattr(setup, "snapshot_disks", lambda p: [disk])
    monkeypatch.setattr(migration, "verify_unmounted_targets", lambda p: None)
    monkeypatch.setattr(migration, "verify_layout", lambda *a: mounts)
    monkeypatch.setattr(migration, "probe_disks", lambda *a: {1})
    monkeypatch.setattr(setup, "confirmation", lambda *a, **k: calls.append("confirm"))

    def run(*args, **kwargs):
        # The intent and original metadata must be readable before execution.
        journal = setup.load_journal(root, plan)
        assert journal.phase == setup.Phase.RUNNING
        assert journal.before == [disk]
        calls.append("encrypt")
        return {"consolidated": []}

    monkeypatch.setattr(in_place, "convert", run)
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
    assert calls == ["confirm", "encrypt"]
    record = setup.load_journal(root, plan)
    assert record.phase == setup.Phase.COMPLETE
    assert record.model_dump(mode="json")["mounts"] == mounts
    before = (root / "provision.json").read_bytes()
    setup.prepare(root)
    setup.provision(root, apply=True)
    assert calls == ["confirm", "encrypt"]
    assert (root / "provision.json").read_bytes() == before


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
    phrase = f"ENCRYPT IN PLACE gc-09 {plan['plan_id'][:12]} test-serial"
    for answer, approved in [("yes", False), (phrase, True)]:
        child = pexpect.spawn(
            str(Path(".venv/bin/python").absolute()),
            ["-c", code],
            encoding="utf-8",
            timeout=15,
        )
        child.expect_exact("> ")
        assert "TARGET COMPUTER: gc-09" in child.before
        assert "serial=test-serial" in child.before
        assert "Data policy (in-place)" in child.before
        child.sendline(answer)
        child.expect(pexpect.EOF)
        assert ("APPROVED" in child.before) is approved
        child.close()
        assert child.exitstatus == (0 if approved else 1)


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

    def denied(*args, **kwargs):
        raise PermissionError("restricted DMI")

    monkeypatch.setattr(Path, "read_text", denied)
    args = (Path(plan["spec"]["checkout"]), "gc-09", "disposable", "discard-approved")
    with pytest.raises(migration.MigrationError, match="do not run Devenv with sudo"):
        setup.observe(*args)
    assert setup.observe(*args, hardware_uuid=spec["hardware_uuid"]) == spec
    with pytest.raises(migration.MigrationError):
        setup.observe(*args, hardware_uuid="")

    assert calls[0][-1] == path
    assert "--nodeps" in calls[0]
    assert setup.snapshot_disks(plan)[0].serial == "test-serial"
    assert "--nodeps" not in calls[-1]
    with pytest.raises(migration.MigrationError):
        setup.observe(
            Path(plan["spec"]["checkout"]),
            "gc-09",
            "disposable",
            "new-disks",
            hardware_uuid=spec["hardware_uuid"],
        )
    with pytest.raises(migration.MigrationError, match="host name"):
        setup.observe(Path("/release"), 'gc-09"; abort', "fresh", "new-disks")


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


def test_autoconf_target_reuses_plan_and_blocks_drift(state, tmp_path):
    import yaml
    from tests.autoconf_test_support import write_config

    root, plan, _ = state
    config_path = write_config(tmp_path)
    raw = yaml.safe_load(config_path.read_text())
    raw["paths"]["nix_output"] = plan["spec"]["checkout"]
    raw["boot_storage"] = {
        "state_root": str(root.parent),
        "hosts": {
            "gc-09": {
                **{
                    k: v
                    for k, v in plan["spec"].items()
                    if k not in {"schema_version", "host", "checkout"}
                },
                "root_encryption": "luks2",
                "installation": "in-place",
            }
        },
    }
    config_path.write_text(yaml.safe_dump(raw))
    spec, selected = setup.configured_target(config_path, "gc-09")
    assert selected == root.parent / "gc-09"
    assert spec["disks"] == plan["spec"]["disks"]
    assert spec["checkout"] == plan["spec"]["checkout"]
    root.rename(selected)
    plan["spec"] = spec
    plan["plan_id"] = migration.digest(
        {k: v for k, v in plan.items() if k != "plan_id"}
    )
    migration.atomic_json(selected / "plan.json", plan)
    assert setup.configured_target(config_path, "gc-09") == (spec, selected)
    raw["boot_storage"]["hosts"]["gc-09"]["disks"][0]["serial"] = "changed"
    config_path.write_text(yaml.safe_dump(raw))
    # An existing plan with different settings must not be adopted implicitly.
    with pytest.raises(
        migration.MigrationError, match="differs from the saved plan in: disks"
    ):
        setup.configured_target(config_path, "gc-09")
    with pytest.raises(migration.MigrationError, match="Add boot_storage.hosts"):
        setup.configured_target(config_path, "gc-02")
    raw["boot_storage"]["state_root"] = None
    config_path.write_text(yaml.safe_dump(raw))
    with pytest.raises(migration.MigrationError, match="no recovery location"):
        setup.configured_target(config_path, "gc-09")


def test_plan_cli_uses_autoconf_without_spec_or_state(monkeypatch, capsys):
    from pathlib import Path

    calls = []
    spec, state = {"host": "gc-09"}, Path("/independent/gc-09")
    monkeypatch.setattr(
        "sys.argv", ["boot-storage-setup", "plan", "--host", "gc-09", "--json"]
    )
    monkeypatch.setattr(setup, "configured_target", lambda p, h: (spec, state))
    monkeypatch.setattr(migration, "plan_spec", lambda s, p: calls.append((s, p)))
    monkeypatch.setattr(setup, "prepare", lambda p: calls.append(p))
    monkeypatch.setattr(
        setup,
        "next_step",
        lambda p: setup.NextStep(
            action=setup.Action.ASSESS,
            host="gc-09",
            plan_id="test",
            reason="Recovery evidence required",
        ),
    )
    setup.main()
    assert calls == [(spec, state), state]
    assert json.loads(capsys.readouterr().out)["action"] == "assess"


def test_guidance_covers_all_existing_assessment_contracts():
    required = {c for checks in migration.STAGES.values() for c in checks} | {
        "new_disks_verified",
        "initial_credentials_staged",
        "whole_disk_image_verified",
        "selected_disks_disposal_authorized",
        "machine_and_application_credentials_preserved_or_reenrolled",
        "in_place_backup_acknowledged",
        "plaintext_remnants_reviewed",
        "container_data_consolidated",
    }
    assert set(setup.guidance()) == required
    assert all(setup.guidance().values())


def test_status_remains_machine_readable(state, monkeypatch, capsys):
    root, plan, _ = state
    monkeypatch.setattr("sys.argv", ["boot-storage-setup", "status", "--host", "gc-09"])
    monkeypatch.setattr(setup, "configured_target", lambda *a: (plan["spec"], root))
    monkeypatch.setattr(migration, "status", lambda p: {"plan_id": plan["plan_id"]})
    setup.main()
    assert json.loads(capsys.readouterr().out) == {"plan_id": plan["plan_id"]}


def test_human_output_explains_recovery_and_exact_next_command(state, capsys):
    root, plan, _ = state
    step = setup.NextStep(
        action=setup.Action.ASSESS,
        host="gc-09",
        plan_id=plan["plan_id"],
        stage="recovery",
        reason="Operator review required",
        required_checks=["console_boot_tested"],
    )
    setup.show_step(step, root, Path("/reviewed/autoconf/config.yml"))
    output = capsys.readouterr().out
    assert "physical console" in output
    assert "boot-storage-setup review" in output
    assert str(root / "recovery-notes.txt") in output
    assert "Rerunning plan will not complete" in output
    assert "--apply" not in output


@pytest.mark.parametrize("answer", ["VERIFIED", "yes"])
def test_review_requires_explicit_checks_and_delegates_attestation(
    state, monkeypatch, answer
):
    root, plan, _ = state
    report = root / "notes.txt"
    report.write_text("Operator tested console and recorded the actual result.")
    step = setup.NextStep(
        action=setup.Action.ASSESS,
        host="gc-09",
        plan_id=plan["plan_id"],
        stage="recovery",
        reason="Operator review required",
        required_checks=["console_boot_tested"],
    )
    monkeypatch.setattr(setup, "next_step", lambda p: step)
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    recorded = []
    monkeypatch.setattr(
        migration,
        "attest",
        lambda s, stage, evidence, assessor: recorded.append(
            (stage, json.loads(evidence.read_text()), assessor)
        ),
    )
    if answer == "VERIFIED":
        setup.review(root, "operator", report)
        assert recorded[0][0] == "recovery"
        assert recorded[0][1]["checks"] == {"console_boot_tested": True}
        assert recorded[0][1]["artifacts"] == [str(report)]
        assert recorded[0][2] == "operator"
    else:
        with pytest.raises(migration.MigrationError, match="cancelled"):
            setup.review(root, "operator", report)
        assert not recorded and not list(root.glob("*-review-*.json"))


def test_review_rejects_piped_approval(state, monkeypatch):
    root, _, _ = state
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: False)
    with pytest.raises(migration.MigrationError, match="interactive"):
        setup.review(root, "operator", root / "notes.txt")


@pytest.mark.parametrize("changed", [False, True])
def test_review_rejects_empty_or_changed_notes(state, monkeypatch, changed):
    root, plan, _ = state
    report = root / "notes.txt"
    report.write_text("actual initial notes" if changed else "")
    step = setup.NextStep(
        action=setup.Action.ASSESS,
        host="gc-09",
        plan_id=plan["plan_id"],
        stage="recovery",
        reason="Review required",
        required_checks=["console_boot_tested"],
    )
    monkeypatch.setattr(setup, "next_step", lambda p: step)
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: True)

    def confirm(prompt):
        report.write_text("changed while reviewing")
        return "VERIFIED"

    monkeypatch.setattr("builtins.input", confirm)
    with pytest.raises(migration.MigrationError, match="changed|actual test results"):
        setup.review(root, "operator", report)
    assert not list(root.glob("*-review-*.json"))


@pytest.fixture
def workflow_environment(state, monkeypatch):
    from lx_administration.storage import recovery_media

    root, plan, _ = state
    calls = []
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(recovery_media, "setup", lambda *a, **k: calls.append("media"))
    monkeypatch.setattr(migration, "plan_spec", lambda *a: calls.append("plan"))
    monkeypatch.setattr(setup, "prepare", lambda *a: calls.append("journal"))
    monkeypatch.setattr(setup, "show_step", lambda *a, **k: None)
    return root, plan, calls


def test_workflow_preview_never_prepares_or_reviews(workflow_environment, monkeypatch):
    root, plan, calls = workflow_environment
    monkeypatch.setattr(
        setup,
        "next_step",
        lambda p: setup.NextStep(
            action=setup.Action.ASSESS,
            host="gc-09",
            plan_id=plan["plan_id"],
            reason="review",
        ),
    )
    setup.run_workflow(plan["spec"], root, Path("/config"), apply=False)
    assert calls == []


@pytest.mark.parametrize("mode", ["disposable", "migration", "fresh", None])
def test_retired_mode_stops_before_recovery_discovery(
    workflow_environment, monkeypatch, mode
):
    from lx_administration.storage import recovery_media
    root, plan, calls = workflow_environment
    spec = plan["spec"] | {"installation": mode}
    monkeypatch.setattr(recovery_media, "setup",
                        lambda *a, **k: pytest.fail("must reject before discovery"))
    with pytest.raises(migration.MigrationError, match="Only in-place"):
        setup.run_workflow(spec, root / "not-created", Path("/config"), apply=False)
    assert not (root / "not-created").exists()
    assert calls == []


@pytest.mark.parametrize(
    "action",
    [
        setup.Action.PROVISION,
        setup.Action.RECOVER,
        setup.Action.PREPARE_ACCESS,
        setup.Action.INSTALL,
    ],
)
def test_installer_guidance_uses_native_python_not_devenv(state, capsys, action):
    root, plan, _ = state
    step = setup.NextStep(
        action=action,
        host="gc-09",
        plan_id=plan["plan_id"],
        reason="Installer required",
    )
    setup.show_step(step, root, Path("/reviewed/config.yml"))
    output = capsys.readouterr().out
    assert "python -m lx_administration.storage.boot_setup" in output
    assert "--config /reviewed/config.yml" in output
    assert "devenv" not in output
    assert "Do not guess or mark it VERIFIED" in output


def test_workflow_pauses_for_notes_then_installer(
    workflow_environment, monkeypatch, capsys
):
    root, plan, calls = workflow_environment
    step = setup.NextStep(
        action=setup.Action.ASSESS,
        host="gc-09",
        plan_id=plan["plan_id"],
        reason="review",
        stage="recovery",
    )
    monkeypatch.setattr(setup, "next_step", lambda p: step)
    setup.run_workflow(plan["spec"], root, Path("/config"), apply=True)
    assert calls == ["media", "plan", "journal"]
    assert "write the completed check results" in capsys.readouterr().out
    (root / "recovery-notes.txt").write_text("Actual results")
    monkeypatch.setattr("builtins.input", lambda prompt: "operator")

    def reviewed(*args):
        calls.append("review")
        step.action = setup.Action.PROVISION
        step.stage = None

    monkeypatch.setattr(setup, "review", reviewed)
    monkeypatch.setattr(setup.os, "geteuid", lambda: 1000)
    setup.run_workflow(plan["spec"], root, Path("/config"), apply=True)
    assert calls[-1] == "review"
    assert "boot installer media" in capsys.readouterr().out


@pytest.mark.parametrize(
    "action", [setup.Action.RECOVER, setup.Action.INSTALL_RECOVERY]
)
def test_workflow_never_retries_interrupted_writes(
    workflow_environment, monkeypatch, action
):
    root, plan, calls = workflow_environment
    monkeypatch.setattr(
        setup,
        "next_step",
        lambda p: setup.NextStep(
            action=action, host="gc-09", plan_id=plan["plan_id"], reason="interrupted"
        ),
    )
    monkeypatch.setattr(setup, "advance", lambda *a, **k: pytest.fail("must not retry"))
    setup.run_workflow(plan["spec"], root, Path("/config"), apply=True)
    assert calls == ["media", "plan", "journal"]


def test_workflow_installs_then_stops_for_physical_boot(
    workflow_environment, monkeypatch, capsys
):
    root, plan, calls = workflow_environment
    monkeypatch.setattr(
        setup,
        "next_step",
        lambda p: setup.NextStep(
            action=setup.Action.INSTALL,
            host="gc-09",
            plan_id=plan["plan_id"],
            reason="ready",
        ),
    )
    monkeypatch.setattr(setup.os, "geteuid", lambda: 0)
    monkeypatch.setattr(migration, "mount_record", lambda p: {"fstype": "tmpfs"})
    monkeypatch.setattr(setup, "advance", lambda *a, **k: calls.append("install"))
    setup.run_workflow(plan["spec"], root, Path("/config"), apply=True)
    assert calls[-1] == "install"
    assert "No automatic reboot" in capsys.readouterr().out


def test_current_host_matches_hostname_or_unique_installer_hardware(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace

    settings = SimpleNamespace(hardware_uuid="known-hardware")
    monkeypatch.setattr(
        setup.AutoconfConfig,
        "load",
        lambda p: SimpleNamespace(
            boot_storage=SimpleNamespace(hosts={"gc-09": settings})
        ),
    )
    monkeypatch.setattr(setup.socket, "gethostname", lambda: "gc-09")
    assert setup.current_host(Path("/config")) == "gc-09"
    hardware = tmp_path / "uuid"
    hardware.write_text("known-hardware")
    monkeypatch.setattr(migration, "DMI_UUID", hardware)
    monkeypatch.setattr(setup.socket, "gethostname", lambda: "nixos")
    assert setup.current_host(Path("/config")) == "gc-09"
    hardware.write_text("unknown-hardware")
    with pytest.raises(migration.MigrationError, match="exactly one"):
        setup.current_host(Path("/config"))


def test_workflow_orders_provision_access_review_install(
    workflow_environment, monkeypatch
):
    root, plan, calls = workflow_environment
    stages = [setup.Action.PROVISION, setup.Action.PREPARE_ACCESS, setup.Action.INSTALL]
    index = [0]
    monkeypatch.setattr(
        setup,
        "next_step",
        lambda p: setup.NextStep(
            action=stages[index[0]],
            stage="prepared" if index[0] == 1 else None,
            host="gc-09",
            plan_id=plan["plan_id"],
            reason="ready",
        ),
    )
    monkeypatch.setattr(setup.os, "geteuid", lambda: 0)
    monkeypatch.setattr(migration, "mount_record", lambda p: {"fstype": "tmpfs"})
    monkeypatch.setattr("builtins.input", lambda prompt: "operator")
    (root / "prepared-notes.txt").write_text("Actual prepared-target checks")

    def advance(*args, **kwargs):
        calls.append(stages[index[0]].value)
        if index[0] == 0:
            index[0] += 1

    def review(*args):
        calls.append("review")
        index[0] += 1

    monkeypatch.setattr(setup, "advance", advance)
    monkeypatch.setattr(setup, "review", review)
    setup.run_workflow(plan["spec"], root, Path("/config"), apply=True)
    assert calls == [
        "media",
        "plan",
        "journal",
        "provision",
        "prepare-access",
        "review",
        "install",
    ]


def test_workflow_apply_requires_terminal_before_media(
    workflow_environment, monkeypatch
):
    root, plan, calls = workflow_environment
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: False)
    with pytest.raises(migration.MigrationError, match="interactive terminal"):
        setup.run_workflow(plan["spec"], root, Path("/config"), apply=True)
    assert calls == []


@pytest.mark.parametrize("mode", ["fresh", "disposable", "migration", None])
@pytest.mark.parametrize("action", ["prepare", "provision", "next_step"])
def test_saved_destructive_plan_cannot_reach_execution(
    state, monkeypatch, mode, action
):
    root, plan, progress = state
    plan["spec"].update(installation=mode, source_retention="old-disks")
    if mode is None:
        del plan["spec"]["installation"]
    else:
        plan["spec"]["source_retention"] = {
            "fresh": "new-disks", "disposable": "discard-approved",
            "migration": "old-disks"
        }[mode]
    plan["plan_id"] = migration.digest(
        {k: v for k, v in plan.items() if k != "plan_id"}
    )
    progress["plan_id"] = plan["plan_id"]
    migration.atomic_json(root / "plan.json", plan)
    migration.atomic_json(root / "progress.json", progress)
    from contextlib import nullcontext
    monkeypatch.setattr(migration, "installer_lock", lambda: nullcontext(1))
    monkeypatch.setattr(migration, "verify_source",
                        lambda *a: pytest.fail("must reject before execution checks"))
    with pytest.raises(migration.MigrationError, match="Only in-place"):
        getattr(setup, action)(root)
    assert not (root / "provision.json").exists()


@pytest.mark.parametrize("mode", ["fresh", "disposable", "migration"])
def test_autoconf_and_cli_reject_destructive_modes(state, monkeypatch, mode):
    from lx_administration.autoconf.config import BootStorageHost
    _, plan, _ = state
    fields = {k: plan["spec"][k] for k in BootStorageHost.model_fields
              if k in plan["spec"]}
    fields.update(root_encryption="luks2", installation=mode)
    with pytest.raises(ValidationError):
        BootStorageHost.model_validate(fields)
    monkeypatch.setattr(setup.sys, "argv", [
        "boot-storage-setup", "observe", "--checkout", "/nonexistent",
        "--host", "gc-09", "--installation", mode, "--source-retention", "in-place",
    ])
    with pytest.raises(SystemExit) as failure:
        setup.main()
    assert failure.value.code == 2


@pytest.mark.parametrize("failure", [RuntimeError("interrupted"), KeyboardInterrupt()])
def test_interrupted_conversion_preserves_journal_and_resumes(
    environment, monkeypatch, failure
):
    from lx_administration.storage import in_place
    root, plan, _, calls, _ = environment
    original = in_place.convert
    def fail(*a, **kw):
        assert setup.load_journal(root, plan).phase == setup.Phase.RUNNING
        raise failure
    monkeypatch.setattr(in_place, "convert", fail)
    with pytest.raises(type(failure)):
        setup.provision(root, apply=True)
    assert setup.load_journal(root, plan).phase == setup.Phase.INTERRUPTED
    assert setup.next_step(root).action == setup.Action.PROVISION
    monkeypatch.setattr(in_place, "root_state", lambda *a: in_place.ENCRYPTING)
    monkeypatch.setattr(in_place, "convert", original)
    setup.provision(root, apply=True)
    assert calls == ["confirm", "confirm", "encrypt"]
    assert setup.load_journal(root, plan).phase == setup.Phase.COMPLETE


def test_output_says_a_plan_is_not_encryption_and_shows_progress(
    state, capsys, monkeypatch
):
    root, _, _ = state

    def missing(state):
        raise migration.MigrationError("run preflight first")

    monkeypatch.setattr(setup.migration, "require_preflight", missing)
    step = setup.next_step(root)
    assert step.action == setup.Action.ASSESS and step.stage == "recovery"
    setup.show_step(step, root, Path("/config.yml"))
    output = capsys.readouterr().out
    assert "[x] Plan saved" in output
    assert "[ ] Secret preflight passed" in output
    assert "Root is NOT encrypted yet" in output
    assert "Nothing has failed" in output
    assert "Do this next: run devenv shell boot-storage-setup" in output


def test_passed_preflight_is_shown_as_done(state, capsys, monkeypatch):
    root, _, _ = state
    monkeypatch.setattr(setup.migration, "require_preflight", lambda state: None)
    setup.show_step(setup.next_step(root), root, Path("/config.yml"))
    output = capsys.readouterr().out
    assert "[x] Secret preflight passed" in output
    assert "Secret preflight has passed" in output
    assert "First prove" not in output


def test_success_keeps_json_output_parseable(capsys):
    setup.success("done")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "SUCCESS: done" in captured.err
