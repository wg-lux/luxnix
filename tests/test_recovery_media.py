"""Recovery-media setup cannot format or silently select unrelated storage."""

import json
from types import SimpleNamespace

import pytest

from lx_administration.storage import recovery_media as media

SPEC = {
    "host": "gc-09",
    "hardware_uuid": "host-uuid",
    "checkout": "/reviewed",
    "disks": [{"path": "/dev/system", "serial": "system"}],
}


def disk(serial="external", tran="usb", fs="ext4", uuid=None):
    return {
        "name": "/dev/" + serial,
        "type": "disk",
        "size": 8 * media.MIN_FREE,
        "fstype": fs,
        "uuid": uuid if uuid is not None else serial + "-uuid",
        "tran": tran,
        "rm": False,
        "ro": False,
        "serial": serial,
        "mountpoints": [],
    }


def discover(monkeypatch, rows):
    monkeypatch.setattr(
        media.migration, "run", lambda *a: json.dumps({"blockdevices": rows})
    )
    return media.discover(SPEC)


def test_selection_excludes_system_unsupported_and_internal(monkeypatch):
    rows = [
        disk(),
        disk("system"),
        disk("internal", "sata"),
        disk("fat", fs="vfat"),
        disk("blank", fs=None),
    ]
    assert [m.serial for m in discover(monkeypatch, rows)] == ["external"]
    rows[0]["ro"] = True
    assert discover(monkeypatch, rows) == []


def test_ambiguity_and_duplicate_uuid_never_choose_first(monkeypatch):
    rows = [disk(), disk("other", uuid="other-uuid")]
    candidates = discover(monkeypatch, rows)
    with pytest.raises(ValueError, match="exactly one"):
        media.select(candidates, None)
    assert media.select(candidates, "/dev/other").serial == "other"
    rows[1]["uuid"] = "external-uuid"
    assert discover(monkeypatch, rows) == []


@pytest.fixture
def setup_environment(tmp_path, monkeypatch):
    mount = tmp_path / "recovery"
    state_root = mount / "luxnix-state"
    monkeypatch.setattr(media, "MOUNT", mount)
    monkeypatch.setattr(media, "STATE_ROOT", state_root)
    selected = media.Medium(
        device="/dev/external",
        uuid="external-uuid",
        filesystem="ext4",
        serial="external",
        size_bytes=8 * media.MIN_FREE,
    )
    monkeypatch.setattr(media, "discover", lambda s: [selected])
    records = [{"target": "/", "source": "/dev/system", "fstype": "ext4"}]
    monkeypatch.setattr(media, "mounts", lambda: records)
    monkeypatch.setattr(media.migration, "source_identity", lambda p: {})
    monkeypatch.setattr(
        media.migration, "device_disks", lambda d: {1} if d == "/dev/system" else {2}
    )
    monkeypatch.setattr(media.migration, "private_path", lambda *a, **kw: None)
    monkeypatch.setattr(
        media.os,
        "statvfs",
        lambda p: SimpleNamespace(f_bavail=2 * media.MIN_FREE, f_frsize=1),
    )
    commands = []

    def privileged(program, *args):
        commands.append(program)
        if program == "cat":
            return "host-uuid"
        if program == "mkdir":
            mount.mkdir()
        if program == "mount":
            records.append(
                {
                    "target": str(mount),
                    "source": selected.device,
                    "fstype": "ext4",
                    "uuid": selected.uuid,
                    "options": "rw,nosuid,nodev",
                }
            )
        if program == "install":
            state_root.mkdir()
        return ""

    monkeypatch.setattr(media, "privileged", privileged)
    return state_root / "gc-09", commands, records, selected


def test_preview_then_setup_and_repeat_preserve_media(setup_environment):
    state, commands, _, _ = setup_environment
    media.setup(SPEC, state, apply=False)
    assert commands == []
    media.setup(SPEC, state, apply=True)
    assert commands == ["cat", "mkdir", "mount", "install"]
    commands.clear()
    media.setup(SPEC, state, apply=True)
    assert commands == ["cat"]


@pytest.mark.parametrize("problem", ["full", "wrong-uuid", "readonly", "target-disk"])
def test_bad_mount_cannot_create_state(setup_environment, monkeypatch, problem):
    state, commands, records, selected = setup_environment
    media.MOUNT.mkdir()
    records.append(
        {
            "target": str(media.MOUNT),
            "source": selected.device,
            "fstype": "ext4",
            "uuid": selected.uuid,
            "options": "rw",
        }
    )
    if problem == "full":
        monkeypatch.setattr(
            media.os, "statvfs", lambda p: SimpleNamespace(f_bavail=0, f_frsize=1)
        )
    elif problem == "wrong-uuid":
        records[-1]["uuid"] = "different"
    elif problem == "readonly":
        records[-1]["options"] = "ro"
    else:
        monkeypatch.setattr(media.migration, "device_disks", lambda d: {1})
    with pytest.raises(ValueError):
        media.setup(SPEC, state, apply=True)
    assert "install" not in commands
    assert not state.parent.exists()


def test_existing_files_are_not_hidden(setup_environment):
    state, commands, _, _ = setup_environment
    media.MOUNT.mkdir()
    (media.MOUNT / "existing").write_text("retain")
    with pytest.raises(ValueError, match="hide existing"):
        media.setup(SPEC, state, apply=True)
    assert commands == ["cat"]


def test_wrong_host_stops_before_mount(setup_environment, monkeypatch):
    state, _, _, _ = setup_environment
    monkeypatch.setattr(media, "privileged", lambda *a: "different-host")
    with pytest.raises(ValueError, match="hardware"):
        media.setup(SPEC, state, apply=True)
    assert not state.parent.exists()


@pytest.mark.parametrize("apply,fail", [(False, False), (True, False), (True, True)])
def test_cli_plans_only_after_successful_media_setup(
    monkeypatch, tmp_path, apply, fail
):
    from lx_administration.storage import boot_setup

    calls = []
    state = tmp_path / "gc-09"
    monkeypatch.setattr(
        "sys.argv",
        ["boot-storage-setup", "setup-media", "--host", "gc-09"]
        + (["--apply"] if apply else []),
    )
    monkeypatch.setattr(boot_setup, "configured_target", lambda *a: (SPEC, state))
    monkeypatch.setattr(boot_setup, "show_target", lambda *a, **k: None)
    monkeypatch.setattr(boot_setup, "show_step", lambda *a, **k: None)

    def prepare_media(*args, **kwargs):
        calls.append("media")
        if fail:
            raise ValueError("mount failed")

    monkeypatch.setattr(media, "setup", prepare_media)
    monkeypatch.setattr(media.migration, "plan_spec", lambda *a: calls.append("plan"))
    monkeypatch.setattr(media.migration, "publish_source", lambda *a: None)
    monkeypatch.setattr(boot_setup, "prepare", lambda *a: calls.append("journal"))
    monkeypatch.setattr(
        boot_setup,
        "next_step",
        lambda *a: boot_setup.NextStep(
            action=boot_setup.Action.ASSESS,
            host="gc-09",
            plan_id="test",
            reason="Evidence required",
        ),
    )
    if fail:
        with pytest.raises(SystemExit) as error:
            boot_setup.main()
        assert error.value.code == 1
    else:
        boot_setup.main()
    assert calls == (["media", "plan", "journal"] if apply and not fail else ["media"])


def test_drive_change_after_mount_cannot_create_state(setup_environment, monkeypatch):
    state, commands, _, selected = setup_environment

    def discover(spec):
        return (
            [selected.model_copy(update={"serial": "changed"})]
            if "mount" in commands
            else [selected]
        )

    monkeypatch.setattr(media, "discover", discover)
    with pytest.raises(ValueError, match="identity changed"):
        media.setup(SPEC, state, apply=True)
    assert "mount" in commands and "install" not in commands
    assert not state.parent.exists()
