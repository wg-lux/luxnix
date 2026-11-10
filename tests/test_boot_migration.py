"""Migration admission rejects missing evidence and never repeats uncertain writes."""

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
    # The receipt gate has its own coverage in test_secret_preflight.py.
    monkeypatch.setattr(migration, "preflight_artifacts", lambda *a: [])
    monkeypatch.setattr(migration, "verify_preflight_artifacts", lambda *a, **k: None)
    root = tmp_path / "state"
    root.mkdir()
    (root / ".lock").touch(mode=0o600)
    spec = {
        "schema_version": 1,
        "host": "gc-09",
        "checkout": "/home/admin/release",
        "hardware_uuid": "12345678-1234-1234-1234-123456789abc",
        "installation": "in-place",
        "source_retention": "in-place",
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


@pytest.mark.parametrize("kind", ["risk-accepted", "restore-tested"])
def test_status_distinguishes_reviewed_backup_outcomes(state, tmp_path, kind):
    root, plan, progress = state
    seed_assessment(state, "recovery", tmp_path)
    backup = {
        "status": kind,
        "accepted_by": "Test operator" if kind == "risk-accepted" else None,
        "location": "/independent-backup" if kind == "restore-tested" else None,
        "restore_test": (
            "Isolated data/key restore" if kind == "restore-tested" else None
        ),
        "verification": (
            "operator-reported" if kind == "restore-tested" else "not-performed"
        ),
    }
    path = root / migration.RECOVERY_CHECKS
    path.write_text(
        json.dumps(
            {
                "plan_id": plan["plan_id"],
                "checks": {"in_place_backup_acknowledged": {"backup": backup}},
            }
        )
    )
    # A provisional answer alone is never a reviewed recovery assessment.
    assert migration.data_recovery(root, plan, progress)["status"] == "unknown"
    progress["attestations"]["recovery"]["artifacts"].append(
        {
            "path": str(path),
            "sha256": migration.file_digest(path),
        }
    )
    migration.atomic_json(root / "progress.json", progress)
    outcome = migration.status(root)["data_recovery"]
    assert outcome == backup | {"current_backup_availability": "not-inspected"}
    # Changing an answer after its review invalidates the outcome.
    path.write_text(path.read_text() + " ")
    assert migration.data_recovery(root, plan, progress)["status"] == "unknown"


@pytest.mark.parametrize(
    "failure", ["legacy", "wrong-plan", "invalid-claim", "expired"]
)
def test_missing_or_invalid_backup_evidence_remains_unknown(state, tmp_path, failure):
    root, plan, progress = state
    seed_assessment(state, "recovery", tmp_path)
    answer = {"detail": "Historical free-text acknowledgement"}
    if failure != "legacy":
        answer["backup"] = {
            "status": "risk-accepted",
            "accepted_by": "Test operator",
            "location": None,
            "restore_test": None,
            "verification": (
                "verified" if failure == "invalid-claim" else "not-performed"
            ),
        }
    path = root / migration.RECOVERY_CHECKS
    path.write_text(
        json.dumps(
            {
                "plan_id": (
                    "another-plan" if failure == "wrong-plan" else plan["plan_id"]
                ),
                "checks": {"in_place_backup_acknowledged": answer},
            }
        )
    )
    progress["attestations"]["recovery"]["artifacts"].append(
        {
            "path": str(path),
            "sha256": migration.file_digest(path),
        }
    )
    if failure == "expired":
        progress["attestations"]["recovery"]["recorded_at"] -= migration.MAX_AGE + 1
    assert migration.data_recovery(root, plan, progress)["status"] == "unknown"


def test_reject_missing_and_changed_prior_evidence(state, tmp_path, monkeypatch):
    root, plan, progress = state
    report, _ = evidence(tmp_path, plan, "prepared")
    with pytest.raises(migration.MigrationError, match="recovery"):
        migration.attest(root, "prepared", report, "Test reviewer")
    _, artifact = seed_assessment(state, "recovery", tmp_path)
    artifact.write_text("Changed report")
    with pytest.raises(migration.MigrationError, match="evidence changed"):
        migration.attest(root, "prepared", report, "Test reviewer")
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


def test_preservation_keeps_vault_recovery_requirement(state, tmp_path):
    root, plan, _ = state
    checks = dict.fromkeys(migration.required_checks("recovery", plan), True)
    assert checks.pop("vault_recovery_tested") is True
    report, _ = evidence(tmp_path, plan, "recovery", checks=checks)
    with pytest.raises(migration.MigrationError, match="Every required"):
        migration.attest(root, "recovery", report, "Test reviewer")
    assert migration.load_progress(root, plan)["attestations"] == {}


def test_identical_assessment_does_not_refresh_clock(state, tmp_path, monkeypatch):
    root, plan, _ = state
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
    report, _ = seed_assessment(state, "recovery", tmp_path)
    seed_assessment(state, "prepared", tmp_path)
    migration.attest(root, "recovery", report, "Another reviewer")
    assert set(migration.load_progress(root, plan)["attestations"]) == {"recovery"}


def test_plan_tampering_and_partial_initialization_fail(state, tmp_path, monkeypatch):
    root, plan, _ = state
    plan["spec"].update(installation="in-place", source_retention="in-place")
    plan["plan_id"] = migration.digest(
        {k: v for k, v in plan.items() if k != "plan_id"}
    )
    migration.atomic_json(root / "plan.json", plan)
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


@pytest.mark.parametrize("stage", ["backup", "restore", "unknown"])
def test_retired_stages_cannot_enter_preservation(state, stage):
    _, plan, _ = state
    with pytest.raises(migration.MigrationError, match="does not apply"):
        migration.required_checks(stage, plan)


def test_source_cleanliness_and_durable_path_are_required(monkeypatch):
    with pytest.raises(migration.MigrationError, match="durable"):
        migration.source_identity(Path("/tmp/disposable-release"))
    monkeypatch.setattr(migration, "run", lambda *a, **k: " M file")
    with pytest.raises(migration.MigrationError, match="uncommitted"):
        migration.source_identity(Path("/home/admin/release"))


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
    monkeypatch.setattr(migration, "verify_root_guard", lambda *a, **k: {})
    monkeypatch.setattr(migration, "verify_booted", lambda *a: None)
    # Install-only fixtures have no provision journal; real journals still decide.
    position = migration.lifecycle_position
    monkeypatch.setattr(
        migration,
        "lifecycle_position",
        lambda state, plan, progress: (
            position(state, plan, progress)
            if (state / "provision.json").exists()
            else {"stage": "verifying", "failed_from": None}
        ),
    )
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
    plan["spec"].update(installation="in-place", source_retention="in-place")
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


def test_sibling_states_share_stable_boundary_without_reusing_state_files(state):
    root, _, _ = state
    original = (root / "plan.json").read_bytes()
    sibling = root.with_name("other-host")
    with migration.locked_state(root) as outer:
        with migration.locked_state(sibling, create=True) as nested:
            assert outer == nested
            assert (sibling / ".lock").is_file()
            assert not (sibling / "plan.json").exists()
    assert (root / "plan.json").read_bytes() == original
    with migration.locked_state(root):
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


@pytest.mark.parametrize(
    "mode,retention", [("fresh", "new-disks"), ("disposable", "discard-approved")]
)
def test_fresh_spec_does_not_enable_migration_stages(state, mode, retention):
    _, plan, _ = state
    plan["spec"].update(installation=mode, source_retention=retention)
    migration.validate_spec(plan["spec"])
    with pytest.raises(migration.MigrationError, match="Only in-place"):
        migration.stage_order(plan)
    with pytest.raises(migration.MigrationError, match="Only in-place"):
        migration.required_checks("recovery", plan)


@pytest.mark.parametrize(
    "mode,retention",
    [
        (None, "old-disks"),
        ("migration", "whole-disk-image"),
        ("fresh", "new-disks"),
        ("disposable", "discard-approved"),
    ],
)
def test_retired_plans_are_read_only_evidence(state, monkeypatch, mode, retention):
    root, plan, progress = state
    plan["spec"].update(installation=mode, source_retention=retention)
    if mode is None:
        plan["spec"].pop("installation")
    plan["plan_id"] = migration.digest(
        {k: v for k, v in plan.items() if k != "plan_id"}
    )
    progress["plan_id"] = plan["plan_id"]
    progress["attestations"] = {"backup": {"historical": "unchanged"}}
    migration.atomic_json(root / "plan.json", plan)
    migration.atomic_json(root / "progress.json", progress)
    before = (root / "progress.json").read_bytes()
    monkeypatch.setattr(migration, "verify_source", lambda *a: pytest.fail("read only"))
    result = migration.status(root)
    assert result["read_only"] is True
    assert result["required_checks"] == {}
    assert result["assessments"] == ["backup"]
    with pytest.raises(migration.MigrationError, match="Only in-place"):
        migration.attest(root, "recovery", root / "missing-evidence", "Test reviewer")
    assert (root / "progress.json").read_bytes() == before


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


def test_disposable_spec_still_requires_explicit_discard(state):
    _, plan, _ = state
    plan["spec"]["installation"] = "disposable"
    with pytest.raises(migration.MigrationError, match="discard-approved"):
        migration.validate_spec(plan["spec"])
    plan["spec"]["source_retention"] = "discard-approved"
    migration.validate_spec(plan["spec"])


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


@pytest.mark.parametrize("changed", [None, "toplevel"])
def test_plan_builds_only_system_closure_and_rejects_build_drift(
    state, tmp_path, monkeypatch, changed
):
    import yaml

    _, original, _ = state
    original["spec"].update(installation="in-place", source_retention="in-place")
    spec_path = tmp_path / "spec.yml"
    spec_path.write_text(yaml.safe_dump(original["spec"]))
    target = tmp_path / "new-state"
    config = original["config"] | {
        "disks": {"root": original["spec"]["disks"][0]["path"]},
        "in_place": {"root_fs_type": "btrfs", "arrays": [], "other_encrypted": []},
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
        assert args[-1].endswith("toplevel")
        return config["closure"]

    monkeypatch.setattr(migration, "run", run)
    if changed:
        with pytest.raises(migration.MigrationError, match="changed during build"):
            migration.create_plan(spec_path, target)
        assert not (target / "plan.json").exists()
    else:
        plan = migration.create_plan(spec_path, target)
        assert "provisioner" not in plan["config"]
        assert "provisioner_sha256" not in plan["config"]
        assert migration.load_plan(target) == plan
        assert migration.create_plan(spec_path, target) == plan
    assert len(calls) == 1


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
    path.chmod(0o664)
    with pytest.raises(migration.MigrationError, match="writable by group or others"):
        migration.private_path(path)
    assert path.stat().st_mode & 0o777 == 0o664


def _trusted_parents(monkeypatch, path):
    from types import SimpleNamespace

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


@pytest.mark.parametrize(
    ("directory", "mode", "expected"),
    [(False, 0o644, 0o600), (False, 0o440, 0o400), (True, 0o755, 0o700)],
)
def test_private_path_tightens_read_only_exposure(
    tmp_path, monkeypatch, capsys, directory, mode, expected
):
    path = tmp_path / "state"
    path.mkdir() if directory else path.write_text("{}")
    path.chmod(mode)
    _trusted_parents(monkeypatch, path)

    migration.private_path(path, directory=directory)
    assert path.stat().st_mode & 0o777 == expected
    assert f"Restricted {path}" in capsys.readouterr().err

    migration.private_path(path, directory=directory)
    assert capsys.readouterr().err == ""


def test_private_path_refuses_foreign_owner_without_changes(tmp_path, monkeypatch):
    path = tmp_path / "progress.json"
    path.write_text("{}")
    path.chmod(0o644)
    _trusted_parents(monkeypatch, path)
    monkeypatch.setattr(migration.os, "geteuid", lambda: os.getuid() + 1)

    with pytest.raises(migration.MigrationError, match=f"{path} is owned by uid"):
        migration.private_path(path)
    assert path.stat().st_mode & 0o777 == 0o644


def test_private_path_names_writable_parent(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text("{}")
    with pytest.raises(migration.MigrationError, match="writable by group or others"):
        migration.private_path(path)


def test_private_path_reports_filesystem_without_permissions(tmp_path, monkeypatch):
    path = tmp_path / "plan.json"
    path.write_text("{}")
    path.chmod(0o644)
    _trusted_parents(monkeypatch, path)
    monkeypatch.setattr(migration.os, "fchmod", lambda fd, mode: None)

    with pytest.raises(migration.MigrationError, match="does not store permissions"):
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


@pytest.mark.parametrize("mode", [None, "migration", "fresh", "disposable"])
def test_retired_plan_cannot_build_or_pass_execution_gates(state, monkeypatch, mode):
    root, plan, progress = state
    if mode is not None:
        plan["spec"]["installation"] = mode
    else:
        plan["spec"].pop("installation", None)
    monkeypatch.setattr(
        migration, "run", lambda *a, **kw: pytest.fail("No command allowed")
    )
    monkeypatch.setattr(
        migration, "verify_source", lambda *a: pytest.fail("No source access")
    )
    for operation in [
        lambda: migration.plan_spec(plan["spec"], root / "new"),
        lambda: migration.check_gates(plan, progress, "provision"),
        lambda: migration.check_gates(plan, progress, "install"),
    ]:
        with pytest.raises(migration.MigrationError, match="Only in-place"):
            operation()
    assert not (root / "new").exists()


def test_acceptance_requires_the_planned_system_to_be_booted(monkeypatch):
    closure = "/nix/store/" + "a" * 32 + "-nixos-system-host"
    monkeypatch.setattr(migration.os.path, "realpath", lambda path: "/nix/store/other")
    with pytest.raises(migration.MigrationError, match="booted the planned system"):
        migration.verify_booted({"config": {"closure": closure}})


def test_acceptance_also_checks_the_live_disk(monkeypatch):
    closure = "/nix/store/" + "a" * 32 + "-nixos-system-host"
    calls = []
    monkeypatch.setattr(migration.os.path, "realpath", lambda path: closure)
    monkeypatch.setattr(
        migration, "verify_root_guard", lambda plan, root, **k: calls.append((root, k))
    )
    migration.verify_booted({"config": {"closure": closure}})
    assert calls == [(Path("/"), {"action": "dry-activate"})]
