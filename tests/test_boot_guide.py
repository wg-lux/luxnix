"""The guided command: it may do the measurable work, never the operator's answers."""

import json
import sys

import pytest

from lx_administration.storage import boot_guide as guide
from lx_administration.storage import boot_migration as migration
from lx_administration.storage import boot_setup as setup


def answers(monkeypatch, *values):
    replies = iter(values)
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))


def commands(monkeypatch):
    """Record privileged and terminal commands; report whatever the test configures."""
    seen, results = [], {}

    def privileged(*command):
        seen.append(command)

        class Result:
            returncode = results.get(command[0], 0)
            stdout = b""

        return Result()

    monkeypatch.setattr(guide.secret_preflight, "privileged", privileged)
    monkeypatch.setattr(guide, "interactive", lambda *c: seen.append(c))
    return seen, results


def test_an_existing_custody_file_is_never_formatted(monkeypatch):
    seen, _ = commands(monkeypatch)
    with pytest.raises(migration.MigrationError, match="refusing to format"):
        guide.create_custody()
    assert not [c for c in seen if "luksFormat" in c]


def test_custody_is_reopened_not_recreated(monkeypatch):
    seen, results = commands(monkeypatch)
    results["mountpoint"] = 1  # not mounted; the file exists and is LUKS
    guide.ensure_custody()
    assert ("cryptsetup", "open", str(guide.CUSTODY_FILE), "luxnix-custody") in seen
    assert not [c for c in seen if "luksFormat" in c or c[0] == "mkfs.ext4"]


def test_mounted_custody_is_not_mounted_again(monkeypatch):
    seen, _ = commands(monkeypatch)
    guide.ensure_custody()
    assert not [c for c in seen if c[0] in {"mount", "cryptsetup"}]


def test_a_new_custody_needs_typed_approval(monkeypatch):
    seen, results = commands(monkeypatch)
    results["test"] = 1  # the file does not exist
    answers(monkeypatch, "yes")
    with pytest.raises(guide.Stopped):
        guide.create_custody()
    assert not [c for c in seen if "luksFormat" in c]


def test_copies_are_proven_by_closing_and_reopening(monkeypatch, tmp_path):
    pair = (tmp_path / "live", tmp_path / "copy")
    monkeypatch.setattr(guide.secret_preflight, "missing_copies", lambda *a: [pair])
    monkeypatch.setattr(guide.secret_preflight, "copy_to_custody", lambda *a: None)
    order = []
    monkeypatch.setattr(guide, "close_custody", lambda: order.append("close"))
    monkeypatch.setattr(guide, "open_custody", lambda: order.append("open"))
    answers(monkeypatch)
    guide.fill_custody(tmp_path, tmp_path, reopenable=True)
    assert order == ["close", "open"]


def step(checks):
    return setup.NextStep(
        action=setup.Action.ASSESS,
        host="gc-09",
        plan_id="plan-a",
        stage="recovery",
        reason="review",
        required_checks=checks,
    )


@pytest.fixture
def checks(monkeypatch, tmp_path):
    monkeypatch.setattr(guide, "measured_detail", lambda check, *a: f"measured {check}")
    monkeypatch.setattr(guide.migration, "atomic_json", lambda path, value: (
        path.write_text(json.dumps(value))
    ))
    return tmp_path


def test_only_typed_verified_confirms_a_check(monkeypatch, checks):
    for reply in ("", "yes", "verified", "y"):
        answers(monkeypatch, reply)
        with pytest.raises(guide.Stopped):
            guide.ask_checks({}, checks, step(["console_boot_tested"]))
    assert not (checks / guide.ANSWERS).exists()


def test_answers_survive_a_reboot_for_the_physical_tests(monkeypatch, checks):
    required = ["console_boot_tested", "trusted_installer_tested"]
    answers(monkeypatch, "VERIFIED", "")
    with pytest.raises(guide.Stopped):
        guide.ask_checks({}, checks, step(required))
    # Only the unanswered check is asked on the next run.
    answers(monkeypatch, "VERIFIED")
    assert set(guide.ask_checks({}, checks, step(required))) == set(required)


def test_answers_do_not_carry_to_another_plan_or_past_a_day(monkeypatch, checks):
    answers(monkeypatch, "VERIFIED")
    guide.ask_checks({}, checks, step(["console_boot_tested"]))
    assert guide.load_answers(checks, "plan-a")
    assert not guide.load_answers(checks, "plan-b")
    now = guide.time.time()
    monkeypatch.setattr(guide.time, "time", lambda: now + guide.ANSWER_LIFETIME + 1)
    assert not guide.load_answers(checks, "plan-a")


def test_measured_checks_come_before_the_reboot(monkeypatch, checks):
    asked = []
    monkeypatch.setattr(
        guide, "measured_detail", lambda check, *a: asked.append(check) or ""
    )
    answers(monkeypatch, *["VERIFIED"] * 2)
    guide.ask_checks(
        {}, checks, step(["trusted_installer_tested", "in_place_backup_acknowledged"])
    )
    assert asked == ["in_place_backup_acknowledged", "trusted_installer_tested"]


def test_backup_on_the_encrypted_disk_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(guide.secret_preflight, "exists", lambda path: True)
    monkeypatch.setattr(
        guide.recovery_custody, "storage_disks", lambda path: {"/dev/sys"}
    )
    answers(monkeypatch, str(tmp_path))
    with pytest.raises(migration.MigrationError, match="not a backup"):
        guide.ask_backup({"disks": [{"path": "/dev/sys"}]})


def test_going_without_a_backup_must_name_who_accepts_it(monkeypatch):
    answers(monkeypatch, "", "")
    with pytest.raises(guide.Stopped):
        guide.ask_backup({"disks": []})
    answers(monkeypatch, "", "A. Operator")
    backup = guide.ask_backup({"disks": []})
    assert backup == {
        "status": "risk-accepted", "accepted_by": "A. Operator",
        "location": None, "restore_test": None, "verification": "not-performed",
    }


def test_untested_backup_does_not_count(monkeypatch, tmp_path):
    monkeypatch.setattr(guide.secret_preflight, "exists", lambda path: True)
    monkeypatch.setattr(
        guide.recovery_custody, "storage_disks", lambda path: {"/dev/usb"}
    )
    monkeypatch.setattr(guide, "measure_size", lambda path: "1G")
    answers(monkeypatch, str(tmp_path), "")
    with pytest.raises(guide.Stopped):
        guide.ask_backup({"disks": []})


def test_tested_backup_records_human_evidence_not_automated_proof(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(guide.secret_preflight, "exists", lambda path: True)
    monkeypatch.setattr(
        guide.recovery_custody, "storage_disks", lambda path: {"/dev/usb"}
    )
    monkeypatch.setattr(guide, "measure_size", lambda path: "1G")
    answers(
        monkeypatch, str(tmp_path), "Stopped writers; restored data and keys offline"
    )
    backup = guide.ask_backup({"disks": []})
    assert backup["status"] == "restore-tested"
    assert backup["verification"] == "operator-reported"
    assert backup["location"] == str(tmp_path)
    assert "not automated verification" in guide.backup_detail(backup)


@pytest.mark.parametrize(
    "status,confirmation,label",
    [
        ("risk-accepted", "ACKNOWLEDGED", "risk accepted; backup not verified"),
        ("restore-tested", "VERIFIED", "restore test reported by operator"),
    ],
)
def test_saved_backup_outcomes_remain_distinct(
    monkeypatch, checks, status, confirmation, label
):
    backup = {
        "status": status,
        "accepted_by": "Operator" if status == "risk-accepted" else None,
        "location": "/backup" if status == "restore-tested" else None,
        "restore_test": (
            "Offline data and key restore" if status == "restore-tested" else None
        ),
        "verification": (
            "operator-reported" if status == "restore-tested" else "not-performed"
        ),
    }
    monkeypatch.setattr(guide, "measured_detail", lambda *a: backup)
    answers(monkeypatch, confirmation)
    saved = guide.ask_checks({}, checks, step([guide.BACKUP_CHECK]))
    record = json.loads((checks / guide.ANSWERS).read_text())
    assert record["checks"][guide.BACKUP_CHECK]["backup"] == backup
    assert guide.load_answers(checks, "plan-a") == saved
    assert label in guide.write_notes(checks, saved).read_text()


def test_waiver_cannot_be_recorded_as_a_verified_backup(monkeypatch, checks):
    monkeypatch.setattr(
        guide,
        "measured_detail",
        lambda *a: {
            "status": "risk-accepted",
            "accepted_by": "Operator",
            "location": None,
            "restore_test": None,
            "verification": "not-performed",
        },
    )
    answers(monkeypatch, "VERIFIED")
    with pytest.raises(guide.Stopped):
        guide.ask_checks({}, checks, step([guide.BACKUP_CHECK]))
    assert not (checks / guide.ANSWERS).exists()


def test_old_free_text_backup_answer_has_unknown_verification(tmp_path):
    notes = guide.write_notes(
        tmp_path,
        {
            guide.BACKUP_CHECK: {
                "confirmed_at": guide.time.time(),
                "detail": "Old backup acknowledgement",
            }
        },
    )
    assert "backup verification unknown" in notes.read_text()
    assert "confirmed" not in notes.read_text()


def test_custody_receipt_does_not_claim_application_data_recovery(tmp_path):
    (tmp_path / migration.PREFLIGHT_RECEIPT).write_text(
        json.dumps(
            {
                "custody": "/custody",
                "items": [{"status": "verified"}],
            }
        )
    )
    detail = guide.measured_detail("vault_recovery_tested", {}, tmp_path)
    assert "verifies credential custody only" in detail
    assert "no application-data backup or restore is established" in detail


def test_interactive_failure_does_not_claim_a_partially_changed_target_is_unchanged(
    monkeypatch,
):
    monkeypatch.setattr(
        guide.subprocess,
        "run",
        lambda *a, **kw: type("Result", (), {"returncode": 1})(),
    )
    with pytest.raises(
        migration.MigrationError, match="may have partially completed"
    ) as caught:
        guide.interactive("cryptsetup", "luksFormat", str(guide.CUSTODY_FILE))
    assert str(guide.CUSTODY_FILE) in str(caught.value)
    assert "nothing was deleted" not in str(caught.value)


def test_patient_data_search_reports_counts_never_file_names(monkeypatch):
    class Result:
        returncode = 0
        stdout = b"/home/admin/Downloads\n/home/admin/Downloads\n/tmp\n"

    calls = []

    def privileged(*command):
        calls.append(command)
        return Result()

    monkeypatch.setattr(guide.secret_preflight, "privileged", privileged)
    total, folders = guide.scan_for_patient_data()
    assert total == 3
    assert folders[0].split() == ["2", "/home/admin/Downloads"]
    assert "%h\n" in calls[0]  # the directory only, never %p
    assert "-xdev" in calls[0]


def test_explicit_guide_uses_this_machine(monkeypatch):
    called = {}
    monkeypatch.setattr(setup, "current_host", lambda config: "gc-09")
    monkeypatch.setattr(
        guide, "run", lambda host, config, **k: called.update(host=host)
    )
    monkeypatch.setattr(sys, "argv", ["boot-storage-setup", "guide"])
    setup.main()
    assert called["host"] == "gc-09"


def test_commands_no_longer_need_a_host(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(setup, "current_host", lambda config: "gc-09")

    def target(config, host):
        seen["host"] = host
        raise ValueError("stop here")

    monkeypatch.setattr(setup, "target_spec", target)
    monkeypatch.setattr(sys, "argv", ["boot-storage-setup", "next"])
    with pytest.raises(SystemExit):
        setup.main()
    assert seen["host"] == "gc-09"


def test_retiring_containers_asks_for_root_itself(monkeypatch):
    executed = {}

    def execvp(program, arguments):
        executed.update(program=program, arguments=arguments)
        raise SystemExit(0)

    monkeypatch.setattr(setup.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(setup.os, "execvp", execvp)
    monkeypatch.setattr(sys, "argv", ["x", "retire-containers", "--apply"])
    with pytest.raises(SystemExit):
        setup.main()
    assert executed["program"] == "sudo"
    assert executed["arguments"][-2:] == ["retire-containers", "--apply"]


def test_custody_mounts_without_suid_devices_or_execution(monkeypatch):
    seen, _ = commands(monkeypatch)
    guide.mount_custody()
    assert ("mount", "-o", "nosuid,nodev,noexec") == seen[-1][:3]


def test_bare_preservation_helper_does_not_begin_migration(monkeypatch, capsys):
    monkeypatch.setattr(guide, "run", lambda *a, **k: pytest.fail("explicit guide required"))
    setup.main([])
    assert "usage:" in capsys.readouterr().out
