"""In-place encryption refuses anything risky before it touches the disk.

The conversion runs on a real disk in nixtest/in_place_encryption_vm_test.
"""

import json
from pathlib import Path
import stat

import pytest

from lx_administration.storage import boot_migration as migration
from lx_administration.storage import boot_password
from lx_administration.storage import boot_setup as setup
from lx_administration.storage import in_place


@pytest.mark.parametrize(
    "value",
    [b"short", b"has-a-hyphen12", b"contains yz letter", "pässphrase1234".encode()],
)
def test_passphrase_that_could_differ_at_the_boot_prompt_is_refused(value):
    with pytest.raises(in_place.InPlaceError):
        in_place.check_passphrase(value)


def test_layout_safe_passphrase_is_accepted():
    in_place.check_passphrase(b"correct horse battle 42")


def layout(**changes):
    return {
        "root_fs_type": "btrfs",
        "arrays": [],
        "other_encrypted": [],
        "containers": [{"name": "luxnix-secrets"}],
        "binds": {},
        "swap_partitions": [],
        "root_device": "/dev/disk/by-partlabel/nixos_root",
    } | changes


def test_supported_layout_is_accepted():
    migration.validate_in_place({"in_place": layout()})


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"root_fs_type": "ext4"}, "Btrfs root only"),
        ({"arrays": ["data"]}, "one root partition"),
        ({"other_encrypted": ["luxnix-data"]}, "one root partition"),
    ],
)
def test_layout_that_would_break_is_refused_at_planning(changes, message):
    with pytest.raises(migration.MigrationError, match=message):
        migration.validate_in_place({"in_place": layout(**changes)})


def spec(**changes):
    return {
        "schema_version": 1,
        "host": "gc-09",
        "checkout": "/home/admin/release",
        "hardware_uuid": "12345678-1234-1234-1234-123456789abc",
        "installation": "in-place",
        "source_retention": "in-place",
        "root_encryption": "luks2",
        "disks": [{"path": "/dev/disk/by-id/test", "serial": "s", "size_bytes": 1000}],
    } | changes


def test_in_place_requires_its_own_retention():
    migration.validate_spec(spec())
    with pytest.raises(migration.MigrationError, match="In-place requires"):
        migration.validate_spec(spec(source_retention="discard-approved"))


def test_in_place_skips_restore_stages_and_requires_backup_notice():
    plan = {"spec": spec()}
    assert migration.stage_order(plan) == ("recovery", "prepared")
    checks = migration.required_checks("recovery", plan)
    assert {"in_place_backup_acknowledged", "plaintext_remnants_reviewed"} <= checks
    assert "vault_recovery_tested" in checks
    assert "selected_disks_disposal_authorized" not in checks
    prepared = migration.required_checks("prepared", plan)
    assert "container_data_consolidated" in prepared
    assert "database_restored" not in prepared


def test_operator_is_told_to_back_up_and_nothing_says_erase(capsys):
    setup.show_target(spec())
    output = capsys.readouterr().out
    assert "TESTED BACKUP FIRST" in output
    assert "nothing is formatted" in output
    assert "erases" not in output


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/var/lib/secrets.luks", "root/var/lib/secrets.luks"),
        ("/home/admin/x", "home/admin/x"),
    ],
)
def test_container_path_is_found_below_its_subvolume(path, expected):
    mounts = {
        "/": {"options": ["subvol=root"]},
        "/home": {"options": ["subvol=home"]},
    }
    assert in_place.subvolume_path(mounts, path) == expected


def test_consolidation_publishes_a_compared_copy_and_keeps_old_content(tmp_path):
    source = tmp_path / "container/managed-secrets"
    source.mkdir(parents=True)
    (source / "salt").write_text("host-issued")
    source.chmod(0o750)
    destination = tmp_path / "root/etc/secrets/vault"
    destination.mkdir(parents=True)
    (destination / "stale").write_text("from the old root")
    marker = tmp_path / "root/state/etc__secrets__vault"
    in_place.consolidate_target(source, destination, marker)
    assert (destination / "salt").read_text() == "host-issued"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o750
    aside = destination.with_name("vault.pre-consolidation")
    assert (aside / "stale").read_text() == "from the old root"
    assert not destination.with_name("vault.consolidating").exists()
    assert marker.exists()
    assert (source / "salt").read_text() == "host-issued"


def test_consolidation_state_never_touches_boot_password_state(tmp_path):
    # Nesting it there once left that directory group-readable, failing the install.
    state = in_place.CONSOLIDATION_STATE
    assert boot_password.STATE not in state.parents
    assert state != boot_password.STATE
    source = tmp_path / "source"
    source.mkdir()
    in_place.consolidate_target(source, tmp_path / "root/target", tmp_path / "s/marker")
    assert stat.S_IMODE((tmp_path / "s").stat().st_mode) == 0o700


def test_empty_mount_point_is_replaced_without_an_aside(tmp_path):
    source = tmp_path / "container/application"
    source.mkdir(parents=True)
    (source / "record").write_text("data")
    destination = tmp_path / "root/var/lib/lx-annotate"
    destination.mkdir(parents=True)
    in_place.consolidate_target(source, destination, tmp_path / "state/marker")
    assert (destination / "record").read_text() == "data"
    assert not destination.with_name("lx-annotate.pre-consolidation").exists()


def test_failed_copy_leaves_the_destination_untouched(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "new").write_text("new")
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "old").write_text("old")
    real = in_place.run

    def fail_compare(*args, **kwargs):
        if args[0] == "diff":
            raise in_place.InPlaceError("differs")
        return real(*args, **kwargs)

    monkeypatch.setattr(in_place, "run", fail_compare)
    marker = tmp_path / "state/marker"
    with pytest.raises(in_place.InPlaceError):
        in_place.consolidate_target(source, destination, marker)
    assert (destination / "old").read_text() == "old"
    assert not (destination / "new").exists()
    assert not marker.exists()


def test_existing_aside_is_never_overwritten(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "old").write_text("old")
    aside = tmp_path / "destination.pre-consolidation"
    aside.mkdir()
    (aside / "earlier").write_text("earlier")
    with pytest.raises(in_place.InPlaceError, match="do not overwrite"):
        in_place.consolidate_target(source, destination, tmp_path / "marker")
    assert (destination / "old").exists()
    assert (aside / "earlier").exists()


def retire_fixture(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    target = tmp_path / "var/lib/lx-annotate"
    target.mkdir(parents=True)
    (target / "record").write_text("data")
    container = tmp_path / "app.luks"
    container.write_text("header")
    monkeypatch.setattr(in_place, "CONSOLIDATION_STATE", state)
    monkeypatch.setattr(in_place, "run", lambda *a, **k: "")
    binds = {str(target): {"volume": "app", "directory": "application"}}
    return (
        [{"name": "app", "container": str(container)}],
        binds,
        container,
        target,
        state,
    )


def test_retire_refuses_while_data_was_not_consolidated(tmp_path, monkeypatch):
    containers, binds, container, _, _ = retire_fixture(tmp_path, monkeypatch)
    with pytest.raises(in_place.InPlaceError, match="not consolidated"):
        in_place.retire_containers(containers, binds)
    assert container.exists()


def test_retire_refuses_while_the_container_is_attached(tmp_path, monkeypatch):
    containers, binds, container, _, _ = retire_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(in_place, "run", lambda *a, **k: "/dev/loop0: attached")
    with pytest.raises(in_place.InPlaceError, match="still attached"):
        in_place.retire_containers(containers, binds)
    assert container.exists()


def test_retire_deletes_only_consolidated_containers(tmp_path, monkeypatch):
    containers, binds, container, target, state = retire_fixture(tmp_path, monkeypatch)
    (state / str(target).strip("/").replace("/", "__")).write_text("consolidated")
    assert in_place.retire_containers(containers, binds) == [str(container)]
    assert not container.exists()
    assert (target / "record").read_text() == "data"


def test_retire_requires_recorded_physical_acceptance(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    (root / ".lock").touch(mode=0o600)
    payload = {
        "schema_version": 1,
        "spec": spec(),
        "source": {"revision": "abc", "lock_sha256": "def"},
        "config": {"in_place": layout(), "crypttab": "", "mounts": {}},
    }
    plan = payload | {"plan_id": migration.digest(payload)}
    migration.atomic_json(root / "plan.json", plan)
    migration.atomic_json(
        root / "progress.json",
        {
            "plan_id": plan["plan_id"],
            "attestations": {},
            "install": {"status": "complete"},
        },
    )
    monkeypatch.setattr(migration, "private_path", lambda *a, **k: None)
    with pytest.raises(migration.MigrationError, match="acceptance"):
        setup.retire_containers(root, apply=True)


def test_swap_is_only_erased_when_it_is_really_swap(monkeypatch):
    calls = []

    class Result:
        def __init__(self, kind):
            self.stdout = kind
            self.returncode = 0

    kinds = {
        "/dev/swap": "swap",
        "/dev/other": "btrfs",
        "/dev/encrypted": "crypto_LUKS",
    }
    monkeypatch.setattr(
        in_place.subprocess, "run", lambda args, **k: Result(kinds[args[-1]])
    )
    monkeypatch.setattr(in_place, "run", lambda *a, **k: calls.append(a) or "")
    assert in_place.erase_plaintext_swap(list(kinds)) == (["/dev/swap"], [])
    assert [c[-1] for c in calls] == ["/dev/swap"]


@pytest.mark.parametrize(
    "kind,required,expected",
    [
        ("btrfs", None, in_place.PLAINTEXT),
        ("crypto_LUKS", [], in_place.ENCRYPTED),
        ("crypto_LUKS", ["online-reencrypt-v2"], in_place.ENCRYPTING),
    ],
)
def test_state_comes_from_the_partition_metadata(monkeypatch, kind, required, expected):
    def fake(*args, **kwargs):
        if args[0] == "blkid":
            return kind
        return json.dumps({"config": {"requirements": {"mandatory": required}}})

    monkeypatch.setattr(in_place, "run", fake)
    assert in_place.root_state("/dev/test") == expected


def test_an_unknown_partition_is_never_touched(monkeypatch):
    monkeypatch.setattr(in_place, "run", lambda *a, **k: "ext4")
    with pytest.raises(in_place.InPlaceError, match="stop and inspect"):
        in_place.root_state("/dev/test")


def test_wrong_container_passphrase_stops_before_the_disk_changes(monkeypatch):
    calls = []
    monkeypatch.setattr(in_place, "root_state", lambda device: in_place.PLAINTEXT)
    monkeypatch.setattr(in_place, "filesystem_uuid", lambda device: "uuid")

    def refuse(*a, **k):
        raise in_place.InPlaceError("does not open")

    monkeypatch.setattr(in_place, "verify_containers_before_change", refuse)
    monkeypatch.setattr(in_place, "shrink_filesystem", lambda d: calls.append("shrink"))
    monkeypatch.setattr(in_place, "encrypt", lambda *a, **k: calls.append("encrypt"))
    with pytest.raises(in_place.InPlaceError):
        in_place.convert(
            layout(),
            {},
            root_passphrase=b"correct horse battle",
            container_passphrases={"luxnix-secrets": b"wrong"},
            root=Path("/nonexistent"),
        )
    assert calls == []


def test_unsafe_root_passphrase_stops_before_anything_else(monkeypatch):
    monkeypatch.setattr(in_place, "root_state", lambda device: in_place.PLAINTEXT)
    with pytest.raises(in_place.InPlaceError, match="boot prompt"):
        in_place.convert(
            layout(),
            {},
            root_passphrase=b"zzzzzzzzzzzzzzzz",
            container_passphrases={},
            root=Path("/nonexistent"),
        )


def test_interrupted_conversion_resumes_and_never_shrinks_again(monkeypatch):
    calls = []
    states = iter([in_place.ENCRYPTING, in_place.ENCRYPTED])
    monkeypatch.setattr(in_place, "root_state", lambda device: next(states))
    monkeypatch.setattr(in_place, "shrink_filesystem", lambda d: calls.append("shrink"))
    monkeypatch.setattr(
        in_place, "encrypt", lambda d, p, *, resume: calls.append(("encrypt", resume))
    )

    class Stop(Exception):
        pass

    def stop(*a, **k):
        raise Stop

    monkeypatch.setattr(in_place, "open_root", stop)
    with pytest.raises(Stop):
        in_place.convert(
            layout(),
            {},
            root_passphrase=b"zz-any-existing-value",
            container_passphrases={},
            root=Path("/nonexistent"),
        )
    assert calls == [("encrypt", True)]


def test_interrupted_journal_offers_resume_not_a_formatter(monkeypatch, tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    (root / ".lock").touch(mode=0o600)
    payload = {
        "schema_version": 1,
        "spec": spec(),
        "source": {"revision": "abc", "lock_sha256": "def"},
        "config": {
            "closure": "/nix/store/" + "a" * 32 + "-nixos-system-gc-09",
            "secure_boot": False,
            "mounts": {},
            "crypttab": "",
            "in_place": layout(),
            "provisioner": "/nix/store/" + "a" * 32 + "-disko",
        },
    }
    plan = payload | {"plan_id": migration.digest(payload)}
    migration.atomic_json(root / "plan.json", plan)
    migration.atomic_json(
        root / "progress.json",
        {
            "plan_id": plan["plan_id"],
            "attestations": {},
            "install": {"status": "pending"},
        },
    )
    monkeypatch.setattr(migration, "private_path", lambda *a, **k: None)
    monkeypatch.setattr(setup.migration, "verify_source", lambda *a: None)
    setup.save_journal(root, setup.Journal(plan_id=plan["plan_id"]))
    record = setup.load_journal(root, plan)
    disk = setup.BlockDevice(
        path="/dev/test",
        type="disk",
        serial="s",
        size=1000,
        fstype=None,
        uuid=None,
        mountpoints=[],
    )
    setup.save_journal(root, record, phase=setup.Phase.RUNNING, before=[disk])
    record = setup.load_journal(root, plan)
    setup.save_journal(root, record, phase=setup.Phase.INTERRUPTED)
    step = setup.next_step(root)
    assert step.action == setup.Action.PROVISION
    assert "resume" in step.reason


def probes(monkeypatch, *results):
    answers = iter(results)

    class Probe:
        def __init__(self, returncode, stdout):
            self.returncode, self.stdout = returncode, stdout

    monkeypatch.setattr(
        in_place.subprocess, "run", lambda *a, **k: Probe(*next(answers))
    )


def test_swap_is_erased_and_other_partitions_are_left_alone(monkeypatch):
    erased = []
    monkeypatch.setattr(in_place, "run", lambda *a, **k: erased.append(a[-1]))
    probes(monkeypatch, (0, "swap\n"), (2, ""), (0, "ext4\n"))
    assert in_place.erase_plaintext_swap(["/a", "/b", "/c"]) == (["/a"], [])
    assert erased == ["/a"]


def test_a_failed_probe_is_reported_without_ending_the_conversion(monkeypatch):
    monkeypatch.setattr(in_place, "run", lambda *a, **k: pytest.fail("never erase"))
    probes(monkeypatch, (1, ""))
    assert in_place.erase_plaintext_swap(["/a"]) == ([], ["/a"])


def test_a_failed_erase_is_reported_without_ending_the_conversion(monkeypatch):
    def fail(*a, **k):
        raise in_place.InPlaceError("blkdiscard failed")

    monkeypatch.setattr(in_place, "run", fail)
    probes(monkeypatch, (0, "swap\n"))
    assert in_place.erase_plaintext_swap(["/a"]) == ([], ["/a"])

