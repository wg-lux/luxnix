"""Root-storage preflight decisions, against synthetic hardware observations."""

import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from lx_administration.storage import root_guard as guard

ROOT = Path(__file__).resolve().parents[1]
UUID = "11111111-2222-3333-4444-555555555555"
DISK = "/dev/disk/by-id/nvme-example_1"
PARTITION = "/dev/disk/by-partlabel/nixos_root"
SYSTEM = "/nix/store/" + "a" * 32 + "-nixos-system-host"


def spec(layout):
    encrypted = layout == "boot-luks"
    device = "/dev/mapper/cryptroot" if encrypted else PARTITION
    return {
        "version": 1,
        "host": "host",
        "layout": layout,
        "root": {
            "partition": PARTITION,
            "fsType": "btrfs",
            "disk": DISK,
            "mapping": "cryptroot" if encrypted else None,
            "expected_luks_uuid": None,
            "require_persistent_disk": True,
        },
        "mounts": {
            "/": {"device": device, "fsType": "btrfs", "subvolume": "root"},
            "/nix": {"device": device, "fsType": "btrfs", "subvolume": "nix"},
            "/boot": {"device": "/dev/null", "fsType": "vfat", "subvolume": None},
        },
        "initrd": {
            "systemd": True,
            "unlocks_root": encrypted,
            "plaintext_bridge": False,
        },
        "bootloader": {
            "kind": "systemd-boot",
            "esp": "/boot",
            "limit": 5,
            "efi_variables": True,
        },
    }


def seen(kind, *, generations=None):
    encrypted = kind == guard.ENCRYPTED
    source = "/dev/mapper/cryptroot" if encrypted else PARTITION
    return {
        "partition": "/dev/nvme0n1p3",
        "partition_number": "259:3",
        "disk": "/dev/nvme0n1",
        "parent": "/dev/nvme0n1",
        "signature": "crypto_LUKS" if encrypted else "btrfs",
        "luks": {"version": 2, "uuid": UUID, "reencrypting": False}
        if encrypted
        else None,
        "mapping": (
            {
                "dm_uuid": f"CRYPT-LUKS2-{UUID.replace('-', '')}-cryptroot",
                "backing": ["259:3"],
            }
            if encrypted
            else None
        ),
        "mounts": {
            "/": {"source": source, "fstype": "btrfs", "fsroot": "/root"},
            "/nix": {"source": source, "fstype": "btrfs", "fsroot": "/nix"},
            "/boot": {"source": "/dev/null", "fstype": "vfat", "fsroot": "/"},
        },
        "receipt": {"uuid": UUID, "matches_header": True} if encrypted else None,
        "esp": {"free": 400 * 1024 * 1024, "needed": 100 * 1024 * 1024},
        "generations": generations
        if generations is not None
        else [{"number": 7, "system": "/nix/store/old", "root": kind, "on_esp": True}],
        "firmware_efi": True,
    }


@pytest.fixture(autouse=True)
def resolve_as_given(monkeypatch):
    monkeypatch.setattr(guard, "resolve", lambda path: path)


def codes(s, o, action="boot", **kwargs):
    return {f.code for f in guard.assess(s, o, action=action, system=SYSTEM, **kwargs)}


def test_plaintext_root_with_legacy_containers_passes():
    assert codes(spec("legacy-containers"), seen(guard.PLAINTEXT)) == set()


def test_encrypted_root_with_boot_luks_passes():
    assert codes(spec("boot-luks"), seen(guard.ENCRYPTED)) == set()


@pytest.mark.parametrize("action", ["boot", "switch", "test", "dry-activate"])
def test_boot_luks_on_plaintext_root_is_refused_for_every_action(action):
    findings = guard.assess(
        spec("boot-luks"), seen(guard.PLAINTEXT), action=action, system=SYSTEM
    )
    assert "root-not-luks" in {f.code for f in findings}
    assert all(f.hard for f in findings if f.code == "root-not-luks")


def test_plaintext_generation_on_encrypted_root_is_refused():
    assert "root-is-luks" in codes(spec("legacy-containers"), seen(guard.ENCRYPTED))


def test_missing_cryptroot_mapping_is_refused():
    observed = seen(guard.ENCRYPTED)
    observed["mapping"] = None
    assert "mapping-missing" in codes(spec("boot-luks"), observed)


def test_mapping_from_another_partition_is_refused():
    observed = seen(guard.ENCRYPTED)
    observed["mapping"]["backing"] = ["8:1"]
    assert "mapping-identity" in codes(spec("boot-luks"), observed)


def test_interrupted_encryption_is_refused():
    observed = seen(guard.ENCRYPTED)
    observed["luks"]["reencrypting"] = True
    assert "root-reencrypting" in codes(spec("boot-luks"), observed)


def test_partition_on_another_disk_is_refused():
    observed = seen(guard.ENCRYPTED)
    observed["parent"] = "/dev/sda"
    assert "partition-identity" in codes(spec("boot-luks"), observed)


def test_missing_partition_stops_all_later_checks():
    observed = seen(guard.ENCRYPTED)
    observed["partition"] = None
    assert codes(spec("boot-luks"), observed) == {"partition-missing"}


def test_transient_disk_name_is_refused_when_the_host_requires_persistence():
    s = spec("boot-luks")
    s["root"]["disk"] = "/dev/nvme0n1"
    assert "disk-not-persistent" in codes(s, seen(guard.ENCRYPTED))
    s["root"]["require_persistent_disk"] = False
    assert "disk-not-persistent" not in codes(s, seen(guard.ENCRYPTED))


def test_kernel_disk_name_is_not_compared_when_not_required():
    # Kernel names change between the installer and the installed system.
    s = spec("boot-luks")
    s["root"]["disk"] = "/dev/vda"
    s["root"]["require_persistent_disk"] = False
    observed = seen(guard.ENCRYPTED)
    observed["parent"] = "/dev/vdb"
    assert "partition-identity" not in codes(s, observed)


def test_uefi_is_required_only_when_efi_variables_are_written():
    observed = seen(guard.PLAINTEXT)
    observed["firmware_efi"] = False
    s = spec("legacy-containers")
    assert "firmware" in codes(s, observed)
    s["bootloader"]["efi_variables"] = False
    assert "firmware" not in codes(s, observed)


def test_pinned_luks_uuid_must_match():
    s = spec("boot-luks")
    s["root"]["expected_luks_uuid"] = "99999999-2222-3333-4444-555555555555"
    assert "luks-uuid" in codes(s, seen(guard.ENCRYPTED))


def test_luks1_header_is_refused():
    observed = seen(guard.ENCRYPTED)
    observed["luks"]["version"] = 1
    assert "luks-header" in codes(spec("boot-luks"), observed)


def test_wrong_subvolume_is_refused():
    observed = seen(guard.ENCRYPTED)
    observed["mounts"]["/nix"]["fsroot"] = "/other"
    assert "subvolume" in codes(spec("boot-luks"), observed)


def test_initrd_without_unlock_is_refused():
    s = spec("boot-luks")
    s["initrd"]["unlocks_root"] = False
    assert "initrd" in codes(s, seen(guard.ENCRYPTED))


def test_untested_recovery_credential_blocks_only_persistent_activation():
    observed = seen(guard.ENCRYPTED)
    observed["receipt"] = None
    assert "recovery-credential" in codes(spec("boot-luks"), observed, "switch")
    assert "recovery-credential" not in codes(
        spec("boot-luks"), observed, "dry-activate"
    )


def test_stale_receipt_after_header_change_is_refused():
    observed = seen(guard.ENCRYPTED)
    observed["receipt"]["matches_header"] = False
    assert "recovery-credential" in codes(spec("boot-luks"), observed)


def test_first_install_needs_no_prior_receipt_or_generation():
    observed = seen(guard.ENCRYPTED, generations=[])
    observed["receipt"] = None
    assert codes(spec("boot-luks"), observed, first_install=True) == set()


def test_plaintext_bridge_is_explicit_and_ends_at_encryption():
    s = spec("boot-luks")
    s["initrd"]["plaintext_bridge"] = True
    assert "root-not-luks" not in codes(s, seen(guard.PLAINTEXT))
    assert "plaintext-bridge" in codes(s, seen(guard.ENCRYPTED))


def test_esp_capacity_reserves_margin():
    observed = seen(guard.PLAINTEXT)
    observed["esp"] = {"free": 100 * 1024 * 1024, "needed": 100 * 1024 * 1024}
    assert "esp-capacity" in codes(spec("legacy-containers"), observed)


def test_unmeasurable_esp_fails_closed():
    observed = seen(guard.PLAINTEXT)
    observed["esp"] = None
    assert "esp" in codes(spec("legacy-containers"), observed)


@pytest.mark.parametrize("limit", [0, 1])
def test_retention_below_two_keeps_no_fallback(limit):
    s = spec("legacy-containers")
    s["bootloader"]["limit"] = limit
    assert "retention" in codes(s, seen(guard.PLAINTEXT))


def test_generations_of_the_other_layout_are_not_a_fallback():
    # After encryption, every retained plaintext generation is unbootable.
    old = [
        {"number": n, "system": f"/nix/store/{n}", "root": "plaintext", "on_esp": True}
        for n in range(3)
    ]
    assert "no-fallback-generation" in codes(
        spec("boot-luks"), seen(guard.ENCRYPTED, generations=old)
    )


def test_compatible_generation_outside_retention_window_is_not_a_fallback():
    window = [
        {"number": 1, "system": "/nix/store/1", "root": "plaintext", "on_esp": True}
    ] + [
        {"number": n, "system": f"/nix/store/{n}", "root": "encrypted", "on_esp": True}
        for n in range(2, 8)
    ]
    s = spec("legacy-containers")
    s["bootloader"]["limit"] = 3
    assert "no-fallback-generation" in codes(
        s, seen(guard.PLAINTEXT, generations=window)
    )


def test_repeated_assessment_is_stable():
    s, observed = spec("boot-luks"), seen(guard.PLAINTEXT)
    before = copy.deepcopy(observed)
    first = guard.assess(s, observed, action="boot", system=SYSTEM)
    assert guard.assess(s, observed, action="boot", system=SYSTEM) == first
    assert observed == before


def test_fstab_decides_generation_layout(tmp_path):
    (tmp_path / "etc").mkdir()
    fstab = tmp_path / "etc/fstab"
    fstab.write_text("# comment\n/dev/mapper/cryptroot / btrfs subvol=root 0 0\n")
    assert guard.root_kind_of_generation(tmp_path) == guard.ENCRYPTED
    fstab.write_text(f"{PARTITION} / btrfs subvol=root 0 0\n")
    assert guard.root_kind_of_generation(tmp_path) == guard.PLAINTEXT
    fstab.write_text("none / tmpfs defaults 0 0\n")
    assert guard.root_kind_of_generation(tmp_path) is None


@pytest.mark.parametrize(
    "entry",
    [
        "/dev/mapper/unknown / btrfs defaults 0 0\n",
        "UUID=unknown / ext4 defaults 0 0\n",
        "/dev/vda1 / ext4 defaults 0 0\n/dev/vdb1 / ext4 defaults 0 0\n",
    ],
)
def test_unknown_or_ambiguous_generation_layout_is_not_plaintext(tmp_path, entry):
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/fstab").write_text(entry)
    assert guard.root_kind_of_generation(tmp_path) is None


@pytest.mark.parametrize("raw", [None, "invalid", "null", "{}", '{"config": null}'])
def test_incomplete_luks_probe_remains_unknown(monkeypatch, raw):
    monkeypatch.setattr(guard, "run", lambda *args: raw)
    assert guard.probe_luks(PARTITION) is None


@pytest.mark.parametrize(
    "signature,luks,label",
    [
        (None, None, "compatibility unknown"),
        ("crypto_LUKS", None, "compatibility unknown"),
        (
            "crypto_LUKS",
            {"version": 2, "uuid": UUID, "reencrypting": True},
            "encryption incomplete",
        ),
    ],
)
def test_status_never_claims_bootability_from_incomplete_evidence(
    monkeypatch, capsys, signature, luks, label
):
    observed = seen(guard.ENCRYPTED)
    observed.update(signature=signature, luks=luks)
    monkeypatch.setattr(guard, "observe", lambda *args, **kwargs: observed)
    monkeypatch.setattr(guard, "mounted_root_state", lambda root: guard.UNKNOWN)
    assert guard.status(spec("boot-luks")) == 1
    output = capsys.readouterr().out
    assert label in output
    assert "bootable" not in output


@pytest.mark.parametrize(
    "mounted_kind,expected_status,label",
    [
        (guard.UNKNOWN, 1, "compatibility unknown"),
        (guard.PLAINTEXT, 1, "compatibility unknown"),
        (guard.ENCRYPTING, 1, "encryption incomplete"),
        (guard.ENCRYPTED, 0, "layout compatible; boot unverified"),
    ],
)
def test_known_partition_header_does_not_prove_mounted_root_compatibility(
    monkeypatch, capsys, mounted_kind, expected_status, label
):
    monkeypatch.setattr(guard, "observe", lambda *args, **kwargs: seen(guard.ENCRYPTED))
    monkeypatch.setattr(guard, "mounted_root_state", lambda root: mounted_kind)
    assert guard.status(spec("boot-luks")) == expected_status
    assert label in capsys.readouterr().out


def test_status_reports_incomplete_filesystem_members_as_unknown(monkeypatch, capsys):
    observed = seen(guard.ENCRYPTED)
    monkeypatch.setattr(guard, "observe", lambda *args, **kwargs: observed)
    monkeypatch.setattr(guard, "probe_mount", lambda root: observed["mounts"]["/"])

    def incomplete(mount):
        raise ValueError("Incomplete Btrfs member evidence")

    monkeypatch.setattr(guard.boot, "filesystem_devices", incomplete)
    assert guard.status(spec("boot-luks")) == 1
    output = capsys.readouterr().out
    assert "Mounted root state: unknown" in output
    assert "compatibility unknown" in output


def override_file(tmp_path, monkeypatch, **fields):
    path = tmp_path / "override.json"
    path.write_text(json.dumps({"system": SYSTEM, "expires": 9e12} | fields))
    path.chmod(0o600)
    monkeypatch.setattr(guard, "OVERRIDE", path)
    monkeypatch.setattr(guard, "audit", lambda event: events.append(event))
    uid = path.stat().st_uid
    real = Path.lstat
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda self: type("S", (), {"st_mode": real(self).st_mode, "st_uid": 0})()
        if self == path and uid
        else real(self),
    )
    return path


events: list = []


def test_override_is_one_shot_audited_and_bound_to_the_closure(tmp_path, monkeypatch):
    events.clear()
    path = override_file(tmp_path, monkeypatch, operator="ops", reason="why")
    soft = [guard.Finding("esp-capacity", "x", False)]
    assert guard.consume_override(SYSTEM, soft, "boot") is True
    assert not path.exists()
    assert events[0]["event"] == "override-used" and events[0]["operator"] == "ops"
    assert guard.consume_override(SYSTEM, soft, "boot") is False


def test_override_for_another_closure_is_rejected(tmp_path, monkeypatch):
    override_file(tmp_path, monkeypatch, system="/nix/store/other")
    assert (
        guard.consume_override(SYSTEM, [guard.Finding("esp", "x", False)], "boot")
        is False
    )


def test_expired_override_is_rejected(tmp_path, monkeypatch):
    override_file(tmp_path, monkeypatch, expires=1)
    assert (
        guard.consume_override(SYSTEM, [guard.Finding("esp", "x", False)], "boot")
        is False
    )


def test_override_cannot_excuse_a_physical_mismatch(tmp_path, monkeypatch):
    path = override_file(tmp_path, monkeypatch)
    assert (
        guard.consume_override(SYSTEM, [guard.Finding("root-not-luks", "x")], "boot")
        is False
    )
    assert path.exists()


def test_refused_generation_is_withdrawn_from_the_profile(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(guard, "run", lambda *a: calls.append(a) or "")
    monkeypatch.setattr(guard, "PROFILE_DIR", tmp_path)
    profile = tmp_path / "system"
    target = tmp_path / "closure"
    target.mkdir()
    (tmp_path / "system-8-link").symlink_to(target)
    profile.symlink_to("system-8-link")
    message = guard.withdraw(str(target.resolve()), Path("/"))
    assert "withdrawn" in message
    assert calls[0][-1] == "--rollback" and calls[1][-2:] == (
        "--delete-generations",
        "8",
    )


def test_unrelated_profile_is_never_withdrawn(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(guard, "run", lambda *a: calls.append(a) or "")
    monkeypatch.setattr(guard, "PROFILE_DIR", tmp_path)
    (tmp_path / "system-8-link").mkdir()
    (tmp_path / "system").symlink_to("system-8-link")
    guard.withdraw("/nix/store/other", Path("/"))
    assert calls == []


def test_supported_entry_points_never_skip_pre_switch_checks():
    for path in (
        "ansible/roles/managed/handlers/main.yml",
        "lx_administration/activation.py",
        "lx_administration/secure_boot.py",
        "modules/home/cli/shells/shared/default.nix",
    ):
        assert "NIXOS_NO_CHECK" not in (ROOT / path).read_text(), path


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_gc_09_contract_matches_its_disk_and_keeps_the_check():
    expression = """
      let f = builtins.getFlake ("git+file://" + toString ./.);
          c = f.nixosConfigurations.gc-09.config;
      in {
        spec = builtins.fromJSON (builtins.readFile
          c.environment.etc."luxnix/root-storage.json".source);
        check = c.system.preSwitchChecks ? rootStorage;
        sudo = c.security.sudo.extraConfig;
      }"""
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    spec_ = state["spec"]
    assert state["check"] is True
    assert "env_keep-=NIXOS_NO_CHECK" in state["sudo"]
    assert spec_["layout"] == "legacy-containers"
    assert spec_["initrd"]["unlocks_root"] is False
    assert spec_["root"]["partition"] == PARTITION
    assert spec_["root"]["disk"].startswith("/dev/disk/by-id/nvme-Phison")
    assert {"/", "/home", "/nix", "/persist", "/var/log", "/boot"} <= spec_[
        "mounts"
    ].keys()
    assert spec_["mounts"]["/persist"]["subvolume"] == "persist"


def test_first_install_rejects_a_stale_receipt():
    observed = seen(guard.ENCRYPTED, generations=[])
    observed["receipt"]["matches_header"] = False
    assert "recovery-credential" in codes(
        spec("boot-luks"), observed, first_install=True
    )


def test_in_place_install_can_require_its_receipt():
    observed = seen(guard.ENCRYPTED, generations=[])
    observed["receipt"] = None
    assert "recovery-credential" in codes(
        spec("boot-luks"), observed, first_install=True, require_receipt=True
    )


def test_generation_without_efi_entry_is_not_a_fallback():
    gens = [
        {"number": 7, "system": "/nix/store/old", "root": "plaintext", "on_esp": False}
    ]
    assert "no-fallback-generation" in codes(
        spec("legacy-containers"), seen(guard.PLAINTEXT, generations=gens)
    )


def boot_entry(esp, number, closure, *, kernel=True):
    entries = esp / "loader/entries"
    entries.mkdir(parents=True, exist_ok=True)
    (esp / "EFI/nixos").mkdir(parents=True, exist_ok=True)
    (esp / "EFI/nixos/initrd.efi").touch()
    if kernel:
        (esp / "EFI/nixos/kernel.efi").touch()
    (entries / f"nixos-generation-{number}.conf").write_text(
        "title NixOS\nlinux /EFI/nixos/kernel.efi\ninitrd /EFI/nixos/initrd.efi\n"
        f"options init={closure}/init root=fstab\n"
    )


def test_esp_generation_scan_reads_what_each_entry_boots(tmp_path):
    boot_entry(tmp_path, 12, SYSTEM)
    linux = tmp_path / "EFI/Linux"
    linux.mkdir(parents=True)
    (linux / "nixos-generation-4-abc.efi").touch()
    (tmp_path / "loader/entries/nixos-generation-9-specialisation-x.conf").touch()
    assert guard.esp_generations(tmp_path) == {12: SYSTEM, 4: None}


def test_entry_with_a_missing_kernel_is_not_usable(tmp_path):
    boot_entry(tmp_path, 12, SYSTEM, kernel=False)
    assert guard.esp_generations(tmp_path) == {}


def test_entry_booting_another_closure_is_not_marked_usable(tmp_path):
    boot_entry(tmp_path / "boot", 3, "/nix/store/" + "b" * 32 + "-nixos-system-other")
    profiles = tmp_path / guard.PROFILE_DIR
    profiles.mkdir(parents=True)
    closure = tmp_path / "closure"
    closure.mkdir()
    (profiles / "system-3-link").symlink_to(closure)
    assert guard.probe_generations(tmp_path)[0]["on_esp"] is False


def test_verify_never_withdraws_or_consumes(monkeypatch, capsys):
    monkeypatch.setattr(guard, "observe", lambda *a, **k: seen(guard.PLAINTEXT))
    monkeypatch.setattr(guard, "withdraw", lambda *a: pytest.fail("withdrew"))
    monkeypatch.setattr(guard, "consume_override", lambda *a: pytest.fail("consumed"))
    assert guard.verify(spec("boot-luks"), system=SYSTEM, action="boot") == 1
    assert "root-not-luks" in capsys.readouterr().err
