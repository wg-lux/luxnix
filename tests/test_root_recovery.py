"""Recovery classification and generation selection; no disks are touched."""

import json
from pathlib import Path

import pytest

from lx_administration.storage import root_recovery as recovery

UUID = "11111111-2222-3333-4444-555555555555"


def luks(reencrypting=False):
    return {"version": 2, "uuid": UUID, "reencrypting": reencrypting}


@pytest.mark.parametrize(
    "signature,luks,expected",
    [
        ("btrfs", None, recovery.PLAINTEXT),
        ("crypto_LUKS", luks(), recovery.ENCRYPTED),
        ("crypto_LUKS", luks(True), recovery.ENCRYPTING),
        ("crypto_LUKS", {"version": 1, "reencrypting": False}, recovery.UNKNOWN),
        ("crypto_LUKS", {"version": 2, "reencrypting": False}, recovery.UNKNOWN),
        ("crypto_LUKS", luks() | {"uuid": "invalid"}, recovery.UNKNOWN),
        ("crypto_LUKS", None, recovery.UNKNOWN),
        (None, None, recovery.UNKNOWN),
        ("swap", None, recovery.UNKNOWN),
    ],
)
def test_state_comes_from_partition_metadata(signature, luks, expected):
    assert recovery.classify(signature, luks) == expected


GENERATIONS = [
    {"number": 4, "system": "/nix/store/plain", "root": "plaintext"},
    {"number": 5, "system": "/nix/store/crypt", "root": "encrypted"},
    {"number": 6, "system": "/nix/store/unknown", "root": None},
]


def test_recovery_after_failed_activation_selects_a_matching_generation():
    assert recovery.choose(recovery.PLAINTEXT, GENERATIONS, 4)["number"] == 4


def test_plaintext_generation_is_never_offered_on_encrypted_disk():
    with pytest.raises(ValueError, match="would not boot"):
        recovery.choose(recovery.ENCRYPTED, GENERATIONS, 4)


def test_encrypted_generation_is_never_offered_on_plaintext_disk():
    with pytest.raises(ValueError, match="would not boot"):
        recovery.choose(recovery.PLAINTEXT, GENERATIONS, 5)


@pytest.mark.parametrize("state", [recovery.ENCRYPTING, recovery.UNKNOWN])
def test_no_generation_is_offered_for_an_unbootable_disk_state(state):
    for number in (4, 5):
        with pytest.raises(ValueError):
            recovery.choose(state, GENERATIONS, number)


def test_unknown_generation_layout_is_refused():
    with pytest.raises(ValueError, match="compatibility cannot be established"):
        recovery.choose(recovery.PLAINTEXT, GENERATIONS, 6)


def test_missing_generation_is_refused():
    with pytest.raises(ValueError, match="not retained"):
        recovery.choose(recovery.PLAINTEXT, GENERATIONS, 99)


def test_every_disk_state_has_a_procedure_and_none_formats():
    for state in (
        recovery.PLAINTEXT,
        recovery.ENCRYPTING,
        recovery.ENCRYPTED,
        recovery.UNKNOWN,
    ):
        steps = " ".join(recovery.PROCEDURES[state]).lower()
        assert steps
        assert "mkfs" not in steps and "luksformat" not in steps


@pytest.fixture
def mounted(monkeypatch):
    monkeypatch.setattr(
        recovery.root_guard,
        "probe_mount",
        lambda root: {
            "source": "/dev/mapper/root",
            "fstype": "btrfs",
            "uuid": UUID,
        },
    )
    monkeypatch.setattr(
        recovery.root_guard.boot, "filesystem_devices", lambda mount: ["/dev/root"]
    )
    monkeypatch.setattr(recovery.root_guard.boot, "require_luks2", lambda device: None)
    monkeypatch.setattr(recovery.root_guard, "probe_luks", lambda device: luks())


def disk(name="/dev/vda"):
    return {"name": name, "type": "disk"}


def encrypted():
    return {
        "name": "/dev/mapper/root",
        "type": "crypt",
        "children": [
            {"name": "/dev/vda1", "type": "part", "children": [disk()]},
        ],
    }


@pytest.mark.parametrize("failure", [None, "", "invalid", "{}", '{"blockdevices": []}'])
def test_failed_ancestry_probe_remains_unknown(mounted, monkeypatch, failure):
    monkeypatch.setattr(recovery.root_guard, "run", lambda *args: failure)
    assert recovery.mounted_root_state(Path("/mnt")) == recovery.UNKNOWN


@pytest.mark.parametrize(
    "node,signature,expected",
    [
        (disk(), "btrfs", recovery.PLAINTEXT),
        (disk(), None, recovery.UNKNOWN),
        (encrypted(), "btrfs", recovery.ENCRYPTED),
        ({"name": "/dev/mapper/root", "type": "crypt"}, "btrfs", recovery.UNKNOWN),
        (
            {"name": "/dev/md0", "type": "raid1", "children": [encrypted(), disk()]},
            "btrfs",
            recovery.UNKNOWN,
        ),
    ],
)
def test_complete_ancestry_required_for_each_member(
    mounted, monkeypatch, node, signature, expected
):
    monkeypatch.setattr(
        recovery.root_guard,
        "run",
        lambda *args: json.dumps({"blockdevices": [node]})
        if args[0] == "lsblk"
        else signature,
    )
    assert recovery.mounted_root_state(Path("/mnt")) == expected


@pytest.mark.parametrize("incomplete", [False, True])
def test_all_filesystem_members_must_be_present_and_protected(
    mounted, monkeypatch, incomplete
):
    def members(mount):
        if incomplete:
            raise ValueError("Incomplete Btrfs member evidence")
        return ["/dev/crypt", "/dev/plain"]

    monkeypatch.setattr(recovery.root_guard.boot, "filesystem_devices", members)
    monkeypatch.setattr(
        recovery.root_guard,
        "run",
        lambda *args: json.dumps(
            {"blockdevices": [encrypted() if args[-1] == "/dev/crypt" else disk()]}
        )
        if args[0] == "lsblk"
        else "btrfs",
    )
    assert recovery.mounted_root_state(Path("/mnt")) == recovery.UNKNOWN


@pytest.mark.parametrize(
    "metadata,state",
    [
        (None, recovery.UNKNOWN),
        (luks(True), recovery.ENCRYPTING),
    ],
)
def test_uncertain_conversion_refuses_restore_before_any_mutation(
    mounted, monkeypatch, metadata, state
):
    monkeypatch.setattr(
        recovery.root_guard,
        "run",
        lambda *args: json.dumps({"blockdevices": [encrypted()]}),
    )
    monkeypatch.setattr(recovery.root_guard, "probe_luks", lambda device: metadata)
    monkeypatch.setattr(
        recovery.root_guard, "probe_generations", lambda root: GENERATIONS
    )
    monkeypatch.setattr(
        recovery.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("must not select a generation"),
    )
    assert recovery.mounted_root_state(Path("/mnt")) == state
    with pytest.raises(ValueError, match=state):
        recovery.restore(Path("/mnt"), 5, apply=True)


def test_mapping_type_failure_remains_unknown(mounted, monkeypatch):
    monkeypatch.setattr(
        recovery.root_guard,
        "run",
        lambda *args: json.dumps({"blockdevices": [encrypted()]}),
    )

    def failed_mapping(device):
        raise ValueError("Protected storage requires an actual LUKS2 mapping")

    monkeypatch.setattr(recovery.root_guard.boot, "require_luks2", failed_mapping)
    assert recovery.mounted_root_state(Path("/mnt")) == recovery.UNKNOWN
