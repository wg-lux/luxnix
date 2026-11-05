"""Migration admission rejects missing evidence and never repeats uncertain writes."""

from datetime import datetime, timezone
import json
from pathlib import Path
import os
import subprocess
import sys
import time

import pytest

from lx_administration.storage import boot_migration as migration


@pytest.fixture
def state(tmp_path, monkeypatch):
    # Test state contains synthetic public metadata, never production secrets.
    monkeypatch.setattr(migration, "private_path", lambda *a, **k: None)
    monkeypatch.setattr(migration, "verify_source", lambda *a: None)
    root = tmp_path / "state"
    root.mkdir()
    (root / ".lock").touch(mode=0o600)
    spec = {
        "schema_version": 1,
        "host": "gc-09",
        "checkout": "/home/admin/release",
        "hardware_uuid": "12345678-1234-1234-1234-123456789abc",
        "source_retention": "old-disks",
        "disks": [
            {
                "path": "/dev/disk/by-id/test-disk",
                "serial": "test-serial",
                "size_bytes": 1000,
            }
        ],
    }
    payload = {
        "schema_version": 1,
        "spec": spec,
        "source": {"revision": "abc", "lock_sha256": "def"},
        "config": {
            "layout": "boot-luks",
            "closure": "/nix/store/" + "a" * 32 + "-nixos-system-gc-09",
            "secure_boot": False,
            "mounts": {},
            "crypttab": "",
        },
    }
    plan = payload | {"plan_id": migration.digest(payload)}
    progress = {
        "plan_id": plan["plan_id"],
        "attestations": {},
        "install": {"status": "pending"},
    }
    migration.atomic_json(root / "plan.json", plan)
    migration.atomic_json(root / "progress.json", progress)
    return root, plan, progress


def evidence(tmp_path, plan, stage, *, checks=None):
    artifact = tmp_path / (stage + "-report.txt")
    artifact.write_text("Synthetic test result, no patient or secret data")
    report = tmp_path / (stage + "-evidence.json")
    report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plan_id": plan["plan_id"],
                "stage": stage,
                "checks": checks
                if checks is not None
                else {key: True for key in migration.required_checks(stage, plan)},
                "artifacts": [str(artifact)],
            }
        )
    )
    return report, artifact


def seed_assessment(state, stage, tmp_path):
    root, plan, progress = state
    report, artifact = evidence(tmp_path, plan, stage)
    progress["attestations"][stage] = {
        "plan_id": plan["plan_id"],
        "kind": "human-attestation",
        "assessor": "Test reviewer",
        "recorded_at": time.time(),
        "checks": sorted(migration.required_checks(stage, plan)),
        "artifacts": [
            {"path": str(p), "sha256": migration.file_digest(p)}
            for p in (report, artifact)
        ],
    }
    migration.atomic_json(root / "progress.json", progress)
    return report, artifact


def test_reject_missing_and_changed_prior_evidence(state, tmp_path, monkeypatch):
    root, plan, progress = state
    report, _ = evidence(tmp_path, plan, "backup")
    with pytest.raises(migration.MigrationError, match="recovery"):
        migration.attest(root, "backup", report, "Test reviewer")
    monkeypatch.setattr(migration, "verify_readiness", lambda *a, **k: None)
    _, artifact = seed_assessment(state, "recovery", tmp_path)
    artifact.write_text("Changed report")
    with pytest.raises(migration.MigrationError, match="evidence changed"):
        migration.attest(root, "backup", report, "Test reviewer")
    assert migration.load_progress(root, plan)["attestations"].keys() == {"recovery"}


def test_human_assessment_requires_exact_checks_and_artifacts(state, tmp_path):
    root, plan, _ = state
    report, _ = evidence(
        tmp_path, plan, "recovery", checks={"console_boot_tested": True}
    )
    with pytest.raises(migration.MigrationError, match="Every required"):
        migration.attest(root, "recovery", report, "Test reviewer")
    report, _ = evidence(tmp_path, plan, "recovery")
    value = json.loads(report.read_text())
    value["artifacts"] = []
    report.write_text(json.dumps(value))
    with pytest.raises(migration.MigrationError, match="without evidence"):
        migration.attest(root, "recovery", report, "Test reviewer")


def test_identical_assessment_does_not_refresh_clock(state, tmp_path, monkeypatch):
    root, plan, _ = state
    monkeypatch.setattr(migration, "verify_readiness", lambda *a, **k: None)
    report, _ = evidence(tmp_path, plan, "recovery")
    migration.attest(root, "recovery", report, "Test reviewer")
    before = (root / "progress.json").read_bytes()
    migration.attest(root, "recovery", report, "Test reviewer")
    assert (root / "progress.json").read_bytes() == before
    progress = migration.load_progress(root, plan)
    progress["attestations"]["recovery"]["recorded_at"] -= migration.MAX_AGE + 1
    migration.atomic_json(root / "progress.json", progress)
    with pytest.raises(migration.MigrationError, match="older than"):
        migration.attest(root, "recovery", report, "Test reviewer")


def test_changed_early_assessment_invalidates_later_assessments(
    state, tmp_path, monkeypatch
):
    root, plan, progress = state
    monkeypatch.setattr(migration, "verify_readiness", lambda *a, **k: None)
    report, _ = seed_assessment(state, "recovery", tmp_path)
    seed_assessment(state, "backup", tmp_path)
    migration.attest(root, "recovery", report, "Another reviewer")
    assert set(migration.load_progress(root, plan)["attestations"]) == {"recovery"}


def test_plan_tampering_and_partial_initialization_fail(state, tmp_path, monkeypatch):
    root, plan, _ = state
    value = json.loads((root / "plan.json").read_text())
    value["spec"]["host"] = "gc-10"
    migration.atomic_json(root / "plan.json", value)
    with pytest.raises(migration.MigrationError, match="content changed"):
        migration.load_plan(root)
    migration.atomic_json(root / "plan.json", plan)
    (root / "progress.json").unlink()
    spec_file = tmp_path / "spec.yml"
    spec_file.write_text(json.dumps(plan["spec"]))
    with pytest.raises(
        migration.MigrationError, match="initialization was interrupted"
    ):
        migration.create_plan(spec_file, root)


def test_whole_disk_retention_adds_required_proof(state):
    _, plan, _ = state
    plan["spec"]["source_retention"] = "whole-disk-image"
    assert "whole_disk_image_verified" in migration.required_checks("backup", plan)


def test_source_cleanliness_and_durable_path_are_required(monkeypatch):
    with pytest.raises(migration.MigrationError, match="durable"):
        migration.source_identity(Path("/tmp/disposable-release"))
    monkeypatch.setattr(migration, "run", lambda *a, **k: " M file")
    with pytest.raises(migration.MigrationError, match="uncommitted"):
        migration.source_identity(Path("/home/admin/release"))


def test_readiness_report_required_and_digest_revalidated(state, tmp_path, monkeypatch):
    _, plan, _ = state
    with pytest.raises(migration.MigrationError, match="exactly one"):
        migration.verify_readiness([], plan)
    report = {"host": "gc-09", "observed_at": datetime.now(timezone.utc).isoformat()}
    report["report_sha256"] = migration.digest(report)
    report["admission"] = {
        "expected_layout": "legacy-containers",
        "expected_serials": ["source-disk"],
    }
    path = tmp_path / "readiness.json"
    path.write_text(json.dumps(report))
    from lx_administration.storage import readiness

    calls = []

    def admit(value, host, layout, serials):
        calls.append((host, layout, serials))
        return {"admitted": True}

    monkeypatch.setattr(readiness, "evaluate", admit)
    migration.verify_readiness([{"path": str(path)}], plan)
    assert calls == [("gc-09", "legacy-containers", ["source-disk"])]
    report["host"] = "gc-10"
    path.write_text(json.dumps(report))
    with pytest.raises(migration.MigrationError, match="digest"):
        migration.verify_readiness([{"path": str(path)}], plan)
    assert len(calls) == 1


def test_readiness_false_admission_and_stale_report_fail(state, tmp_path, monkeypatch):
    _, plan, _ = state
    from lx_administration.storage import readiness

    report = {"host": "gc-09", "observed_at": "2000-01-01T00:00:00+00:00"}
    report["report_sha256"] = migration.digest(report)
    report["admission"] = {
        "admitted": True,
        "expected_layout": "legacy-containers",
        "expected_serials": ["source"],
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    monkeypatch.setattr(readiness, "evaluate", lambda *a: {"admitted": False})
    with pytest.raises(migration.MigrationError, match="fails admission"):
        migration.verify_readiness([{"path": str(path)}], plan)
    monkeypatch.setattr(readiness, "evaluate", lambda *a: {"admitted": True})
    with pytest.raises(migration.MigrationError, match="last 24 hours"):
        migration.verify_readiness([{"path": str(path)}], plan)


@pytest.fixture
def install_environment(state, tmp_path, monkeypatch):
    monkeypatch.setattr(migration.os, "geteuid", lambda: 0)
    actual_fstat = os.fstat

    def root_fstat(fd):
        values = list(actual_fstat(fd))
        values[4] = 0
        return os.stat_result(values)

    monkeypatch.setattr(migration.os, "fstat", root_fstat)
    monkeypatch.setattr(migration, "INSTALL_LOCK", tmp_path / "installer.lock")
    monkeypatch.setattr(migration, "check_gates", lambda *a: {1})
    monkeypatch.setattr(migration, "verify_independent_state", lambda *a: None)
    monkeypatch.setattr(
        migration, "verify_target", lambda *a: {"/": {"uuid": "test-root"}}
    )
    monkeypatch.setattr(migration, "confirm", lambda *a: None)
    original_is_dir = Path.is_dir
    monkeypatch.setattr(
        Path,
        "is_dir",
        lambda p: True if str(p).startswith("/nix/store/") else original_is_dir(p),
    )
    original_resolve = Path.resolve
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda p, **kw: Path(state[1]["config"]["closure"])
        if str(p) == "/mnt/nix/var/nix/profiles/system"
        else original_resolve(p, **kw),
    )
    return state


def test_install_failure_retains_uncertain_state_and_refuses_repeat(
    install_environment, monkeypatch
):
    root, plan, _ = install_environment
    calls = []

    def fail(argv, **kwargs):
        calls.append(argv)
        assert kwargs["pass_fds"], "child must retain the global lock"
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(migration.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        migration.install(root)
    assert migration.load_progress(root, plan)["install"]["status"] == "interrupted"
    with pytest.raises(migration.MigrationError, match="previous installation"):
        migration.install(root)
    with pytest.raises(migration.MigrationError, match="install-recovery"):
        migration.install(root, retry_interrupted=True)
    assert len(calls) == 1
    assert calls[0] == [
        "nixos-install",
        "--root",
        "/mnt",
        "--system",
        plan["config"]["closure"],
        "--no-root-passwd",
    ]


def test_successful_install_is_not_repeated(install_environment, monkeypatch):
    root, plan, _ = install_environment
    calls = []
    monkeypatch.setattr(
        migration.subprocess, "run", lambda argv, **kw: calls.append(argv)
    )
    migration.install(root)
    migration.install(root)
    assert len(calls) == 1
    assert migration.load_progress(root, plan)["install"]["status"] == "complete"


def test_post_confirmation_target_change_prevents_install(
    install_environment, monkeypatch
):
    root, plan, _ = install_environment
    probes = iter([{"/": {"uuid": "original"}}, {"/": {"uuid": "changed"}}])
    monkeypatch.setattr(migration, "verify_target", lambda *a: next(probes))
    monkeypatch.setattr(
        migration.subprocess, "run", lambda *a, **k: pytest.fail("install must not run")
    )
    with pytest.raises(migration.MigrationError, match="Target changed"):
        migration.install(root)
    assert migration.load_progress(root, plan)["install"]["status"] == "pending"


def test_second_state_cannot_bypass_global_lock(install_environment):
    root, _, _ = install_environment
    with migration.installer_lock():
        with pytest.raises(migration.MigrationError, match="Another installer"):
            migration.install(root)


def test_interrupted_running_marker_requires_human_review(install_environment):
    root, plan, progress = install_environment
    progress["install"]["status"] = "running"
    migration.atomic_json(root / "progress.json", progress)
    with pytest.raises(migration.MigrationError, match="previous installation"):
        migration.install(root)
    assert migration.load_progress(root, plan)["install"]["status"] == "interrupted"


def test_signed_first_install_is_rejected(state, monkeypatch):
    _, plan, progress = state
    plan["config"]["secure_boot"] = True
    monkeypatch.setattr(migration, "check_attestation", lambda *a: None)
    monkeypatch.setattr(
        migration,
        "probe_disks",
        lambda *a: pytest.fail("unsupported install must stop before device probing"),
    )
    with pytest.raises(migration.MigrationError, match="Signed first installation"):
        migration.check_gates(plan, progress, "install")


def test_wrong_hardware_fails_before_disk_probe(state, tmp_path, monkeypatch):
    _, plan, _ = state
    hardware = tmp_path / "uuid"
    hardware.write_text("different-machine")
    monkeypatch.setattr(migration, "DMI_UUID", hardware)
    monkeypatch.setattr(
        migration,
        "run",
        lambda *a: pytest.fail("wrong hardware must stop before probing disks"),
    )
    with pytest.raises(migration.MigrationError, match="not the hardware"):
        migration.probe_disks(plan)


def test_evidence_on_target_disk_is_rejected(state, monkeypatch):
    root, _, progress = state
    monkeypatch.setattr(
        migration,
        "run",
        lambda *a: json.dumps(
            {"filesystems": [{"source": "/dev/mapper/evidence", "fstype": "ext4"}]}
        ),
    )
    monkeypatch.setattr(migration, "device_disks", lambda *a: {1})
    with pytest.raises(migration.MigrationError, match="independent storage"):
        migration.verify_independent_state(root, progress, {1})


def test_noninteractive_install_confirmation_refused(state, monkeypatch):
    _, plan, _ = state
    monkeypatch.setattr(migration.sys.stdin, "isatty", lambda: False)
    with pytest.raises(migration.MigrationError, match="interactive"):
        migration.confirm(plan)


@pytest.mark.parametrize(
    "device",
    [
        {"name": "/dev/test", "type": "disk", "mountpoints": ["/old-root"]},
        {
            "name": "/dev/test",
            "type": "disk",
            "mountpoints": [None],
            "children": [
                {"name": "/dev/mapper/open", "type": "crypt", "mountpoints": [None]}
            ],
        },
    ],
)
def test_provision_check_rejects_mounted_or_open_targets(state, monkeypatch, device):
    _, plan, _ = state
    monkeypatch.setattr(
        migration, "run", lambda *a: json.dumps({"blockdevices": [device]})
    )
    with pytest.raises(migration.MigrationError, match="open mapping or mounted"):
        migration.verify_unmounted_targets(plan)


def test_child_keeps_global_lock_when_parent_closes_it(install_environment):
    child = None
    try:
        with migration.installer_lock() as fd:
            child = subprocess.Popen(
                [sys.executable, "-c", "import sys; sys.stdin.read()"],
                stdin=subprocess.PIPE,
                pass_fds=(fd,),
            )
        with pytest.raises(migration.MigrationError, match="Another installer"):
            with migration.installer_lock():
                pytest.fail("child must retain the operation lock")
    finally:
        if child:
            child.communicate(input=b"", timeout=10)
    with migration.installer_lock():
        pass


def test_post_confirmation_evidence_change_stops_before_install(
    install_environment, monkeypatch
):
    root, _, _ = install_environment
    calls = []

    def gates(*args):
        calls.append(args)
        if len(calls) == 2:
            raise migration.MigrationError("Evidence changed")
        return {1}

    monkeypatch.setattr(migration, "check_gates", gates)
    monkeypatch.setattr(
        migration.subprocess, "run", lambda *a, **k: pytest.fail("install must not run")
    )
    with pytest.raises(migration.MigrationError, match="Evidence changed"):
        migration.install(root)
    assert len(calls) == 2


def test_root_mode_requires_luks2(state):
    _, plan, _ = state
    migration.validate_selection({}, {"layout": "boot-luks"})
    for mode in ("none", "unknown"):
        with pytest.raises(migration.MigrationError, match="require root_encryption"):
            migration.validate_selection(
                {"root_encryption": mode}, {"layout": "boot-luks"}
            )
        with pytest.raises(migration.MigrationError, match="require root_encryption"):
            migration.validate_spec(plan["spec"] | {"root_encryption": mode})
    with pytest.raises(migration.MigrationError, match="selection differs"):
        migration.validate_selection({}, {"layout": "unencrypted-root"})


def test_fresh_encrypted_install_keeps_recovery_without_source_restore(state):
    _, plan, _ = state
    plan["spec"].update(
        root_encryption="luks2", installation="fresh", source_retention="new-disks"
    )
    migration.validate_spec(plan["spec"])
    assert migration.stage_order(plan) == ("recovery", "prepared")
    prepared = migration.required_checks("prepared", plan)
    assert {"initial_credentials_staged", "recovery_slots_tested"} <= prepared
    assert "database_restored" not in prepared
    assert "new_disks_verified" in migration.required_checks("recovery", plan)
    assert "secondary_unlock_passed" in migration.required_checks("acceptance", plan)
    with pytest.raises(migration.MigrationError, match="does not apply"):
        migration.required_checks("backup", plan)


def test_fresh_admission_does_not_require_a_nonexistent_source_host(
    state, tmp_path, monkeypatch
):
    root, plan, progress = state
    plan["spec"].update(
        root_encryption="luks2", installation="fresh", source_retention="new-disks"
    )
    plan["config"]["layout"] = "boot-luks"
    plan["plan_id"] = migration.digest(
        {k: v for k, v in plan.items() if k != "plan_id"}
    )
    progress["plan_id"] = plan["plan_id"]
    migration.atomic_json(root / "plan.json", plan)
    migration.atomic_json(root / "progress.json", progress)
    monkeypatch.setattr(
        migration, "verify_readiness", lambda *a, **k: pytest.fail("no existing host")
    )
    report, _ = evidence(tmp_path, plan, "recovery")
    migration.attest(root, "recovery", report, "Test reviewer")
    report, _ = evidence(tmp_path, plan, "prepared")
    migration.attest(root, "prepared", report, "Test reviewer")
    assert set(migration.load_progress(root, plan)["attestations"]) == {
        "recovery",
        "prepared",
    }


@pytest.mark.parametrize("fstype", ["ext4", "crypto_LUKS"])
def test_fresh_plan_cannot_treat_existing_filesystems_as_empty(
    state, monkeypatch, fstype
):
    _, plan, _ = state
    plan["spec"].update(installation="fresh", source_retention="new-disks")
    monkeypatch.setattr(
        migration,
        "run",
        lambda *a: json.dumps(
            {
                "blockdevices": [
                    {
                        "type": "disk",
                        "fstype": None,
                        "children": [
                            {"type": "part", "fstype": fstype, "mountpoints": []}
                        ],
                    }
                ]
            }
        ),
    )
    with pytest.raises(migration.MigrationError, match="empty new disks"):
        migration.verify_unmounted_targets(plan)


def test_disposable_reinstall_requires_explicit_retention_and_recovery(state):
    _, plan, _ = state
    plan["spec"]["installation"] = "disposable"
    with pytest.raises(migration.MigrationError, match="discard-approved"):
        migration.validate_spec(plan["spec"])
    plan["spec"]["source_retention"] = "discard-approved"
    migration.validate_spec(plan["spec"])
    assert migration.stage_order(plan) == ("recovery", "prepared")
    assert migration.required_checks("recovery", plan) == {
        "console_boot_tested",
        "trusted_installer_tested",
        "independent_credentials_tested",
        "selected_disks_disposal_authorized",
        "machine_and_application_credentials_preserved_or_reenrolled",
    }
    assert "initial_credentials_staged" in migration.required_checks("prepared", plan)


@pytest.mark.parametrize(
    "mounted,mapping", [(True, False), (False, True), (False, False)]
)
def test_disposable_disks_still_require_offline_unmapped_target(
    state, monkeypatch, mounted, mapping
):
    _, plan, _ = state
    plan["spec"].update(installation="disposable", source_retention="discard-approved")
    tree = {
        "blockdevices": [
            {
                "type": "crypt" if mapping else "disk",
                "fstype": "btrfs",
                "mountpoints": ["/"] if mounted else [],
            }
        ]
    }
    monkeypatch.setattr(migration, "run", lambda *args: json.dumps(tree))
    if mounted or mapping:
        with pytest.raises(migration.MigrationError, match="open mapping or mounted"):
            migration.verify_unmounted_targets(plan)
    else:
        migration.verify_unmounted_targets(plan)


@pytest.mark.parametrize("changed", [None, "toplevel", "diskoScript"])
def test_plan_pins_provisioner_and_rejects_build_drift(
    state, tmp_path, monkeypatch, changed
):
    import yaml

    _, original, _ = state
    spec_path = tmp_path / "spec.yml"
    spec_path.write_text(yaml.safe_dump(original["spec"]))
    target = tmp_path / "new-state"
    script = tmp_path / "disko"
    script.write_text("reviewed synthetic program")
    config = original["config"] | {
        "disks": {"root": original["spec"]["disks"][0]["path"]},
        "provisioner": str(script),
    }
    monkeypatch.setattr(migration, "source_identity", lambda p: original["source"])
    monkeypatch.setattr(migration, "evaluate", lambda *a: config)
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        assert "--no-update-lock-file" in args
        assert "--no-link" in args
        if changed and args[-1].endswith(changed):
            return "/changed/program"
        return str(script) if args[-1].endswith("diskoScript") else config["closure"]

    monkeypatch.setattr(migration, "run", run)
    if changed:
        with pytest.raises(migration.MigrationError, match="changed during build"):
            migration.create_plan(spec_path, target)
        assert not (target / "plan.json").exists()
    else:
        plan = migration.create_plan(spec_path, target)
        assert plan["config"]["provisioner_sha256"] == migration.file_digest(script)
        assert migration.load_plan(target) == plan
        assert migration.create_plan(spec_path, target) == plan
    assert len(calls) == (1 if changed == "toplevel" else 2)


def test_plaintext_journal_keeps_permissions_guard(tmp_path, monkeypatch):
    from types import SimpleNamespace

    path = tmp_path / "journal.json"
    path.write_text("{}")
    path.chmod(0o600)
    # Model trusted parents; pytest's /tmp parent is otherwise intentionally rejected.
    real_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda p, **kw: (
            SimpleNamespace(st_mode=real_stat(p, **kw).st_mode & ~0o022)
            if p in path.parents
            else real_stat(p, **kw)
        ),
    )
    monkeypatch.setattr(
        migration,
        "encrypted_storage",
        lambda p: pytest.fail("metadata needs no encryption"),
    )
    migration.private_path(path)
    path.chmod(0o644)
    with pytest.raises(migration.MigrationError, match="private"):
        migration.private_path(path)


def test_plaintext_independent_state_is_accepted(state, monkeypatch):
    root, _, progress = state
    monkeypatch.setattr(
        migration,
        "run",
        lambda *a: json.dumps(
            {"filesystems": [{"source": "/dev/usb1", "fstype": "ext4"}]}
        ),
    )
    monkeypatch.setattr(migration, "device_disks", lambda *a: {2})
    migration.verify_independent_state(root, progress, {1})
