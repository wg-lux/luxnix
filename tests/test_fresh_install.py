"""Fresh installation must never inherit migration approval or erase on retry."""

from contextlib import contextmanager
import json
from pathlib import Path

import pytest

from lx_administration import cli
from lx_administration.storage import fresh_install as fresh
from lx_administration.storage import boot_migration as migration
from lx_administration.storage import secret_preflight


def spec(mode="fresh"):
    return {
        "schema_version": 1,
        "host": "test-host",
        "checkout": "/release",
        "hardware_uuid": "12345678-1234-1234-1234-123456789012",
        "installation": mode,
        "source_retention": {
            "fresh": "new-disks",
            "disposable": "discard-approved",
            "in-place": "in-place",
        }[mode],
        "disks": [
            {"path": "/dev/disk/by-id/test", "serial": "TEST", "size_bytes": 4096}
        ],
    }


def test_preservation_profile_cannot_reach_installer():
    with pytest.raises(fresh.Error, match="use migrate"):
        fresh.validate_profile(spec("in-place"))
    fresh.validate_profile(spec())
    fresh.validate_profile(spec("disposable"))


def test_discard_authorization_is_explicit():
    value = spec("disposable")
    value["source_retention"] = "in-place"
    with pytest.raises(fresh.Error, match="discard-approved"):
        fresh.validate_profile(value)


def test_cli_dispatch_is_separate(monkeypatch):
    calls = []
    monkeypatch.setattr(fresh, "main", calls.append)
    cli.main(["install", "--profile", "host.yml"])
    assert calls == [["--profile", "host.yml"]]


@contextmanager
def unlocked(*args, **kwargs):
    yield 123


@pytest.fixture
def execution(monkeypatch, tmp_path):
    plan = {
        "spec": spec("disposable"),
        "source": {"revision": "abc"},
        "config": {
            "admin": {"hash_file": "/admin"},
            "closure": "/closure",
            "mounts": {},
        },
        "disko_script": "/disko",
        "partition_devices": [],
    }
    monkeypatch.setattr(migration, "installer_lock", unlocked)
    monkeypatch.setattr(migration, "locked_state", unlocked)
    monkeypatch.setattr(fresh, "preflight", lambda *a: ({1}, {"/admin": b"hash"}))
    monkeypatch.setattr(secret_preflight, "verify_admin_password", lambda *a: None)
    monkeypatch.setattr(fresh, "confirm", lambda *a: None)
    calls = []
    monkeypatch.setattr(fresh.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(migration, "verify_layout", lambda *a: {"/": "uuid"})
    monkeypatch.setattr(migration, "verify_target", lambda *a: {"/": "uuid"})
    monkeypatch.setattr(fresh, "publish_credentials", lambda *a: None)
    return plan, tmp_path, calls


def test_cancel_never_runs_disko(execution, monkeypatch):
    plan, state, calls = execution

    def cancel(*a):
        raise fresh.Error("cancelled")

    monkeypatch.setattr(fresh, "confirm", cancel)
    with pytest.raises(fresh.Error, match="cancelled"):
        fresh.install(plan, state, state, apply=True)
    assert not calls
    assert not (state / "fresh-install.json").exists()


def test_changed_disk_after_prompt_never_runs_disko(execution, monkeypatch):
    plan, state, calls = execution
    probes = iter([({1}, {"/admin": b"hash"}), ({2}, {"/admin": b"hash"})])
    monkeypatch.setattr(fresh, "preflight", lambda *a: next(probes))
    with pytest.raises(fresh.Error, match="changed"):
        fresh.install(plan, state, state, apply=True)
    assert not calls


@pytest.mark.parametrize(
    "status", ["formatting", "interrupted", "installed-awaiting-cold-boot"]
)
def test_any_existing_attempt_refuses_formatting(execution, status):
    plan, state, calls = execution
    (state / "fresh-install.json").write_text(json.dumps({"status": status}))
    with pytest.raises(fresh.Error, match="already started"):
        fresh.install(plan, state, state, apply=True)
    assert not calls


def test_failure_durable_before_child_and_never_reformatted(execution, monkeypatch):
    plan, state, calls = execution

    def failure(*args, **kwargs):
        assert (
            json.loads((state / "fresh-install.json").read_text())["status"]
            == "formatting"
        )
        assert kwargs["pass_fds"] == (123,)
        assert "IN_DISKO_TEST" not in kwargs["env"]
        assert "password" not in kwargs["env"]
        calls.append(args)
        raise fresh.Error("power lost")

    monkeypatch.setenv("IN_DISKO_TEST", "1")
    monkeypatch.setenv("password", "must-not-inherit")
    monkeypatch.setattr(fresh.subprocess, "run", failure)
    with pytest.raises(fresh.Error, match="power lost"):
        fresh.install(plan, state, state, apply=True)
    assert (
        json.loads((state / "fresh-install.json").read_text())["status"]
        == "interrupted"
    )
    with pytest.raises(fresh.Error, match="already started"):
        fresh.install(plan, state, state, apply=True)
    assert len(calls) == 1


def test_wrong_admin_password_prevents_erasure(execution, monkeypatch):
    plan, state, calls = execution

    def refuse(*a):
        raise fresh.Error("wrong password")

    monkeypatch.setattr(secret_preflight, "verify_admin_password", refuse)
    with pytest.raises(fresh.Error, match="wrong password"):
        fresh.install(plan, state, state, apply=True)
    assert not calls


def test_preview_never_locks_or_creates_state(execution, monkeypatch, capsys):
    plan, state, calls = execution
    monkeypatch.setattr(migration, "probe_disks", lambda *a: {1})
    monkeypatch.setattr(migration, "verify_installer", lambda *a: None)
    monkeypatch.setattr(migration, "verify_unmounted_targets", lambda *a: None)
    fresh.install(plan, state / "absent", state, apply=False)
    assert not calls and not (state / "absent").exists()
    assert "No changes made" in capsys.readouterr().out


def test_mutable_plan_is_rejected(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text("{}")
    with pytest.raises(fresh.Error, match="immutable"):
        fresh.load_plan(plan)


def test_credential_copy_never_overwrites_existing(tmp_path, monkeypatch):
    # Redirect only the fixed installation root; exercise actual exclusive writes.
    original = fresh.Path
    monkeypatch.setattr(
        fresh, "Path", lambda p: tmp_path if p == "/mnt" else original(p)
    )
    monkeypatch.setattr(fresh, "encrypted_storage", lambda p: None)
    fresh.publish_credentials({"/secret/key": b"existing"})
    with pytest.raises(FileExistsError):
        fresh.publish_credentials({"/secret/key": b"replacement"})
    assert (tmp_path / "secret/key").read_bytes() == b"existing"
    assert (tmp_path / "secret/key").stat().st_mode & 0o777 == 0o600


def test_credential_destination_cannot_escape(tmp_path, monkeypatch):
    original = fresh.Path
    monkeypatch.setattr(
        fresh, "Path", lambda p: tmp_path if p == "/mnt" else original(p)
    )
    (tmp_path / "secret").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(fresh.Error, match="symbolic"):
        fresh.publish_credentials({"/secret/key": b"secret"})


def test_nix_literals_preserve_interpolation_characters():
    assert fresh.nix_string("serial-${danger}") == '"serial-\\${danger}"'


def test_inspect_dispatch_does_not_enter_migration(monkeypatch):
    calls = []
    monkeypatch.setattr(fresh, "main", calls.append)
    cli.main(["inspect", "gc-02"])
    assert calls == [["--inspect", "gc-02"]]


def test_current_host_credential_contract_evaluates():
    # Exercise the actual Nix option graph: retired application LUKS options
    # previously made every annotation-host plan fail during evaluation.
    config = migration.evaluate(Path(__file__).resolve().parents[1], "gc-02")
    paths = {item["path"] for item in config["secret_contract"]["items"]}
    assert config["admin"]["hash_file"] in paths
    assert not {"encrypted-data-key", "encrypted-data-uuid"} & {
        item["id"] for item in config["secret_contract"]["items"]
    }


def test_inspect_refuses_wrong_live_mount(monkeypatch):
    import socket
    from lx_administration.storage import boot

    monkeypatch.setattr(socket, "gethostname", lambda: "test-host")
    monkeypatch.setattr(
        migration,
        "evaluate",
        lambda *a: {
            "mounts": {
                "/": {
                    "device": "/dev/mapper/cryptroot",
                    "fsType": "btrfs",
                    "options": [],
                }
            },
            "crypttab": "",
        },
    )

    def wrong(*args, **kwargs):
        raise ValueError("Wrong backing device")

    monkeypatch.setattr(boot, "verify_mount", wrong)
    monkeypatch.setattr(
        migration, "verify_accounts", lambda *a: pytest.fail("stop first")
    )
    with pytest.raises(ValueError, match="Wrong backing device"):
        fresh.inspect("test-host", Path("/release"))


def test_foreign_partition_label_is_rejected_before_formatting(monkeypatch):
    plan = {
        "partition_devices": ["/dev/disk/by-partlabel/root"],
        "config": {"mounts": {}},
    }
    monkeypatch.setattr(fresh.os.path, "exists", lambda p: True)
    monkeypatch.setattr(migration, "device_disks", lambda p: {2})
    with pytest.raises(fresh.Error, match="another disk"):
        fresh.verify_named_devices(plan, {1})
    fresh.verify_named_devices(plan, {2})


def test_migration_journal_is_never_reused(execution):
    plan, state, calls = execution
    (state / "plan.json").write_text("preservation evidence")
    with pytest.raises(fresh.Error, match="Migration state"):
        fresh.install(plan, state, state, apply=True)
    assert not calls
    assert (state / "plan.json").read_text() == "preservation evidence"


@pytest.mark.parametrize(
    "crypttab", ["", "\n \n", "# no secondary disks\n  # root only\n"]
)
def test_root_only_inspection_accepts_empty_contract(monkeypatch, crypttab, capsys):
    from lx_administration.storage import boot

    calls = []
    monkeypatch.setattr("socket.gethostname", lambda: "test-host")
    monkeypatch.setattr(
        migration,
        "evaluate",
        lambda *a: {
            "mounts": {
                "/": {
                    "device": "/dev/mapper/cryptroot",
                    "fsType": "btrfs",
                    "options": [],
                }
            },
            "crypttab": crypttab,
        },
    )
    monkeypatch.setattr(boot, "verify_mount", lambda *a, **k: calls.append("mount"))
    monkeypatch.setattr(
        boot, "verify_unlock", lambda *a: pytest.fail("no secondary disk")
    )
    monkeypatch.setattr(
        migration, "verify_accounts", lambda *a: calls.append("account")
    )
    fresh.inspect("test-host", Path("/release"))
    assert calls == ["mount", "account"]
    assert "no changes made" in capsys.readouterr().out


@pytest.mark.parametrize(
    "crypttab", ["data /dev/disk/by-id/data", "data /dev/data /key luks extra"]
)
def test_inspection_rejects_malformed_substantive_contract(monkeypatch, crypttab):
    monkeypatch.setattr("socket.gethostname", lambda: "test-host")
    monkeypatch.setattr(
        migration, "evaluate", lambda *a: {"mounts": {}, "crypttab": crypttab}
    )
    with pytest.raises(fresh.Error, match="secondary-key contract"):
        fresh.inspect("test-host", Path("/release"))


@pytest.fixture
def recovery(execution, monkeypatch):
    plan, state, calls = execution
    monkeypatch.setattr(migration, "private_path", lambda *a, **k: None)
    monkeypatch.setattr(migration, "probe_disks", lambda *a: {1})
    monkeypatch.setattr(migration, "verify_installer", lambda *a: None)
    monkeypatch.setattr(fresh, "independent", lambda *a: None)
    monkeypatch.setattr(fresh, "credential_files", lambda *a: {"/admin": b"hash"})
    monkeypatch.setattr(fresh, "verify_credential_copies", lambda *a: None)
    monkeypatch.setattr(fresh, "publish_credentials", lambda *a, **k: None)
    original_path = fresh.Path
    monkeypatch.setattr(
        fresh,
        "Path",
        lambda p: (
            FakeProfile()
            if p == "/mnt/nix/var/nix/profiles/system"
            else original_path(p)
        ),
    )
    return plan, state, calls


class FakeProfile:
    def resolve(self):
        return "/closure"


@pytest.mark.parametrize("interrupt", ["credentials", "install"])
def test_resume_continues_checkpoint_without_formatting(
    recovery, monkeypatch, interrupt
):
    plan, state, calls = recovery
    original_publish = fresh.publish_credentials

    def fail_publish(*a, **k):
        raise fresh.Error("interrupted credential copy")

    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "nixos-install" and interrupt == "install":
            raise fresh.Error("interrupted system installation")

    monkeypatch.setattr(fresh.subprocess, "run", run)
    if interrupt == "credentials":
        monkeypatch.setattr(fresh, "publish_credentials", fail_publish)
    with pytest.raises(fresh.Error, match="interrupted"):
        fresh.install(plan, state, state, apply=True)
    record = json.loads((state / "fresh-install.json").read_text())
    assert record["status"] == "interrupted" and record["mounts"] == {"/": "uuid"}
    monkeypatch.setattr(fresh, "publish_credentials", original_publish)
    monkeypatch.setattr(fresh.subprocess, "run", lambda args, **k: calls.append(args))
    before = (state / "fresh-install.json").read_bytes()
    fresh.install(plan, state, state, apply=False, resume=True)
    assert (state / "fresh-install.json").read_bytes() == before
    fresh.install(plan, state, state, apply=True, resume=True)
    assert sum(args[0] == "/disko" for args in calls) == 1
    assert (
        json.loads((state / "fresh-install.json").read_text())["status"]
        == "installed-awaiting-cold-boot"
    )


@pytest.mark.parametrize(
    "change", ["plan", "mounts", "checkpoint", "hardware", "credentials"]
)
def test_resume_refuses_changed_or_uncertain_target(recovery, monkeypatch, change):
    plan, state, calls = recovery
    record = {
        "plan_id": migration.digest(plan),
        "status": "interrupted",
        "mounts": {"/": "uuid"},
    }
    if change == "plan":
        record["plan_id"] = "other-plan"
    elif change == "mounts":
        record["mounts"] = {"/": "other-filesystem"}
    elif change == "checkpoint":
        record.pop("mounts")
    elif change == "hardware":
        monkeypatch.setattr(
            migration,
            "probe_disks",
            lambda *a: (_ for _ in ()).throw(fresh.Error("wrong hardware")),
        )
    else:
        monkeypatch.setattr(
            fresh,
            "verify_credential_copies",
            lambda *a: (_ for _ in ()).throw(fresh.Error("conflicting credential")),
        )
    (state / "fresh-install.json").write_text(json.dumps(record))
    before = (state / "fresh-install.json").read_bytes()
    with pytest.raises(fresh.Error):
        fresh.install(plan, state, state, apply=True, resume=True)
    assert not calls
    assert (state / "fresh-install.json").read_bytes() == before


def test_partial_credentials_preserved_and_conflicts_precede_missing_writes(
    tmp_path, monkeypatch
):
    original = fresh.Path
    monkeypatch.setattr(
        fresh, "Path", lambda p: tmp_path if p == "/mnt" else original(p)
    )
    monkeypatch.setattr(fresh, "encrypted_storage", lambda *a: None)
    monkeypatch.setattr(migration, "target_private", lambda p: tmp_path / p.lstrip("/"))
    fresh.publish_credentials({"/key": b"original"})
    before = (tmp_path / "key").stat()
    fresh.publish_credentials({"/key": b"original", "/other": b"missing"}, resume=True)
    after = (tmp_path / "key").stat()
    assert before.st_ino == after.st_ino and before.st_mtime_ns == after.st_mtime_ns
    with pytest.raises(fresh.Error, match="differs"):
        fresh.publish_credentials(
            {"/new": b"must-not-write", "/key": b"replacement"}, resume=True
        )
    assert not (tmp_path / "new").exists()


def test_fresh_children_inherit_global_and_stable_state_locks(recovery, monkeypatch):
    plan, state, calls = recovery

    @contextmanager
    def state_lock(*args, **kwargs):
        yield 456

    def run(args, **kwargs):
        assert kwargs["pass_fds"] == (123, 456)
        calls.append(args)

    monkeypatch.setattr(migration, "locked_state", state_lock)
    monkeypatch.setattr(fresh.subprocess, "run", run)
    fresh.install(plan, state, state, apply=True)
    assert [args[0] for args in calls] == ["/disko", "nixos-install"]


def test_gc10_both_installation_workflows_evaluate():
    config = migration.evaluate(Path(__file__).resolve().parents[1], "gc-10")
    assert len(config["disks"]) == 2
    assert config["in_place"]["arrays"] == []
    assert config["in_place"]["secondary"] == [
        {
            "name": "luxnix-app-storage",
            "device": "/dev/disk/by-partlabel/btrfs_data01_p1",
            "fs_type": "btrfs",
        }
    ]
    assert "/run/media/admin/Backup-24-11" not in config["mounts"]
    assert (
        config["mounts"]["/var/lib/lx-annotate"]["device"]
        == "/dev/mapper/luxnix-app-storage"
    )
    migration.validate_in_place(config)
    fresh.validate_config(config)


def test_multidisk_preparation_requires_exact_selection(monkeypatch, tmp_path):
    import yaml

    value = spec("disposable")
    profile = tmp_path / "profile.yml"
    profile.write_text(yaml.safe_dump(value))
    monkeypatch.setattr(migration, "source_identity", lambda p: {})
    monkeypatch.setattr(
        migration,
        "evaluate",
        lambda *a: {"disks": {"system": "/dev/system", "data": "/dev/data"}},
    )
    monkeypatch.setattr(fresh, "validate_config", lambda c: None)
    monkeypatch.setattr(migration, "run", lambda *a, **k: pytest.fail("no build"))
    with pytest.raises(fresh.Error, match="every evaluated"):
        fresh.prepare(profile)
