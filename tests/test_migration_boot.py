"""Boot artifact safety tests; never touch real firmware or storage."""

import copy
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from lx_administration.storage import migration_boot as boot
from lx_administration.yaml import load_unique_yaml_file


@pytest.fixture
def spec():
    return {
        "host": "test-host",
        "hardware_uuid": "11111111-1111-4111-8111-111111111111",
        "revision": "a" * 40,
        "interface": "eth0",
        "address": "192.0.2.10/24",
        "gateway": None,
        "controller_cidr": "192.0.2.1/32",
        "authorized_keys": ["ssh-ed25519 AAAA test-fixture"],
        "recovery": {"uuid": "1111-2222", "fstype": "vfat", "luks_uuid": None},
        "target_serials": ["root-disk"],
        "policy": load_unique_yaml_file(Path("conf/migration-environment.yml")),
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("host", "host;reboot"),
        ("revision", "main"),
        ("interface", "eth0;reboot"),
        ("controller_cidr", "0.0.0.0/0"),
        ("authorized_keys", []),
        ("gateway", "198.51.100.1"),
        ("hardware_uuid", "wrong-machine"),
        ("boot_trust", "skip-all-checks"),
        ("console", "pts/0"),
    ],
)
def test_invalid_signed_spec_refused(spec, field, value):
    spec[field] = value
    with pytest.raises(ValueError):
        boot.validate_spec(spec)


def test_publish_is_immutable_and_refuses_symlinks(tmp_path):
    destination = tmp_path / "image.efi"
    boot.publish(destination, b"signed")
    boot.publish(destination, b"signed")
    with pytest.raises(ValueError, match="differs"):
        boot.publish(destination, b"changed")
    alias = tmp_path / "alias.efi"
    alias.symlink_to(destination)
    with pytest.raises(ValueError, match="symlink"):
        boot.publish(alias, b"changed")
    assert destination.read_bytes() == b"signed"


@pytest.fixture
def stage(tmp_path, monkeypatch, spec):
    image = tmp_path / "source.efi"
    image.write_bytes(b"signed test image")
    payload = tmp_path / "payload.squashfs"
    payload.write_bytes(b"test runtime")
    spec["payload"] = {"sha256": boot.digest(payload), "size": payload.stat().st_size}
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    esp = tmp_path / "esp"
    (esp / "loader").mkdir(parents=True)
    (esp / "loader/loader.conf").write_text("default nixos-generation-*\n")
    args = SimpleNamespace(
        host=spec["host"],
        image=image,
        sha256=boot.digest(image),
        certificate=tmp_path / "db.pem",
        esp=esp,
        apply=False,
        allow_unverified_boot=False,
        payload=payload,
        recovery=recovery,
    )
    variables = {"LoaderInfo": "systemd-boot 259"}
    calls = []

    def run(*command):
        calls.append(tuple(map(str, command)))
        if command[0] == "blkid":
            return "/dev/recovery\n"
        if command[0] == "lsblk":
            return '{"blockdevices":[{"type":"disk","serial":"recovery-disk"}]}'
        if command[0] == "findmnt" and recovery in command:
            return json.dumps(
                {
                    "filesystems": [
                        {
                            "source": "/dev/recovery",
                            "uuid": "1111-2222",
                            "fstype": "vfat",
                            "fsroot": "/",
                        }
                    ]
                }
            )
        if command[0] == "findmnt":
            return '{"filesystems":[{"fstype":"vfat"}]}'
        if "list" in command:
            return '[{"id":"nixos-generation-1.conf"}]'
        if "set-oneshot" in command:
            variables["LoaderEntryOneShot"] = command[-1]
        return ""

    original_open = boot.os.open
    monkeypatch.setattr(
        boot.os,
        "open",
        lambda path, *a, **kw: original_open(
            tmp_path / "stage.lock"
            if str(path) == "/run/luxnix-migration-boot.lock"
            else path,
            *a,
            **kw,
        ),
    )
    monkeypatch.setattr(boot.os, "geteuid", lambda: 0)
    monkeypatch.setattr(boot, "image_spec", lambda _: copy.deepcopy(spec))
    monkeypatch.setattr(boot, "require_machine", lambda *a: None)
    monkeypatch.setattr(boot, "loader_variable", variables.get)
    monkeypatch.setattr(boot.sb, "run", run)
    monkeypatch.setattr(
        boot.shutil, "disk_usage", lambda _: SimpleNamespace(free=2**30)
    )
    return args, variables, calls


def test_stage_preview_leaves_esp_and_firmware_unchanged(stage):
    args, variables, calls = stage
    boot.stage(args)
    assert set(args.esp.rglob("*")) == {
        args.esp / "loader",
        args.esp / "loader/loader.conf",
    }
    assert "LoaderEntryOneShot" not in variables
    assert not any("set-oneshot" in call for call in calls)


def test_apply_arms_only_once_and_retains_normal_default(stage):
    args, variables, calls = stage
    args.apply = True
    boot.stage(args)
    boot.stage(args)
    assert variables["LoaderEntryOneShot"].startswith("luxnix-migration-test-host-")
    assert (
        args.esp / "loader/loader.conf"
    ).read_text() == "default nixos-generation-*\n"
    assert len(list((args.esp / "EFI/LuxNixMigration").glob("*.efi"))) == 1
    assert not (args.esp / "EFI/Linux").exists()
    assert not any("set-default" in call or "reboot" in call for call in calls)


@pytest.mark.parametrize("default", ["*", "@saved", "missing-*", "luxnix-migration-*"])
def test_unsafe_normal_default_prevents_publication(stage, default):
    args, variables, calls = stage
    args.apply = True
    variables["LoaderEntryDefault"] = default
    with pytest.raises(ValueError, match="default"):
        boot.stage(args)
    assert not (args.esp / "EFI").exists()


def test_foreign_oneshot_preserved(stage):
    args, variables, calls = stage
    args.apply = True
    variables["LoaderEntryOneShot"] = "other-recovery.conf"
    with pytest.raises(ValueError, match="already armed"):
        boot.stage(args)
    assert variables["LoaderEntryOneShot"] == "other-recovery.conf"
    assert not (args.esp / "EFI").exists()


def test_insufficient_esp_space_never_publishes(stage, monkeypatch):
    args, variables, calls = stage
    args.apply = True
    monkeypatch.setattr(
        boot.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=0 if path == args.esp else 2**30),
    )
    with pytest.raises(ValueError, match="ESP lacks space"):
        boot.stage(args)
    assert not (args.esp / "EFI").exists()
    assert "LoaderEntryOneShot" not in variables


def test_disabled_firmware_trust_and_low_ram_refused(spec, monkeypatch):
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path: spec["hardware_uuid"]
        if path.name == "product_uuid"
        else "MemTotal: 1024 kB\n",
    )

    def disabled(*a):
        raise boot.sb.SecureBootError("Secure Boot disabled")

    monkeypatch.setattr(boot.sb, "firmware_check", disabled)
    with pytest.raises(boot.sb.SecureBootError, match="disabled"):
        boot.require_machine(spec, spec["host"], Path("unused"))
    monkeypatch.setattr(boot.sb, "firmware_check", lambda *a: None)
    with pytest.raises(ValueError, match="Insufficient RAM"):
        boot.require_machine(spec, spec["host"], Path("unused"))


def test_tampered_or_unsigned_image_cannot_change_boot(stage, monkeypatch):
    args, variables, calls = stage
    args.apply = True
    args.image.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA256"):
        boot.stage(args)
    assert calls == []
    args.sha256 = boot.digest(args.image)

    def failed_signature(*a):
        raise boot.sb.SecureBootError("invalid signature")

    monkeypatch.setattr(boot.sb, "run", failed_signature)
    with pytest.raises(boot.sb.SecureBootError, match="signature"):
        boot.stage(args)
    assert not (args.esp / "EFI").exists()


def test_wrong_machine_refused_before_firmware_check(spec, monkeypatch):
    monkeypatch.setattr(
        Path, "read_text", lambda *a: "22222222-2222-4222-8222-222222222222"
    )
    with pytest.raises(ValueError, match="physical machine"):
        boot.require_machine(spec, spec["host"], Path("unused"))


@pytest.mark.parametrize("root,swap", [("btrfs", ""), ("tmpfs", "/dev/test")])
def test_admission_rejects_disk_root_and_swap(spec, tmp_path, monkeypatch, root, swap):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    monkeypatch.setattr(boot, "require_machine", lambda *a: None)
    monkeypatch.setattr(boot.sb, "run", lambda *a: root if a[0] == "findmnt" else swap)
    with pytest.raises(ValueError):
        boot.admit(SimpleNamespace(spec=path, certificate=Path("unused")))


def test_metadata_is_data_not_executable(spec, tmp_path, monkeypatch):
    spec["payload"] = {"sha256": "a" * 64, "size": 100}

    def extract(*args):
        assert args[1:4] == ("--only-section=.osrel", "-O", "binary")
        destination = Path(args[-1])
        assert destination != args[-2], "objcopy must not rewrite its input image"
        destination.write_text(
            "ID=luxnix-migration\nLUXNIX_MIGRATION_SPEC="
            + json.dumps(json.dumps(spec))
            + "\n"
        )

    monkeypatch.setattr(boot.sb, "run", extract)
    assert boot.image_spec(tmp_path / "unused.efi") == spec


def test_changed_payload_never_arms_boot(stage):
    args, variables, calls = stage
    args.apply = True
    args.payload.write_bytes(b"wrong runtime")
    with pytest.raises(ValueError, match="Payload differs"):
        boot.stage(args)
    assert "LoaderEntryOneShot" not in variables
    assert not (args.esp / "EFI").exists()


@pytest.mark.parametrize("failure", ["target", "unknown", "uuid", "encryption"])
def test_recovery_identity_refusal_prevents_boot_changes(stage, monkeypatch, failure):
    args, variables, calls = stage
    args.apply = True
    original = boot.sb.run

    def run(*command):
        result = original(*command)
        if command[0] == "lsblk":
            if failure == "encryption":
                return json.dumps(
                    {
                        "blockdevices": [
                            {"type": "crypt"},
                            {"type": "disk", "serial": "external"},
                        ]
                    }
                )
            serial = "root-disk" if failure == "target" else None
            if failure in {"target", "unknown"}:
                return json.dumps(
                    {"blockdevices": [{"type": "disk", "serial": serial}]}
                )
        if failure == "uuid" and command[0] == "findmnt" and args.recovery in command:
            return result.replace("1111-2222", "3333-4444")
        return result

    monkeypatch.setattr(boot.sb, "run", run)
    with pytest.raises(ValueError, match="Recovery"):
        boot.stage(args)
    assert "LoaderEntryOneShot" not in variables
    assert not (args.esp / "EFI").exists()


@pytest.mark.parametrize(
    "failure", [None, "digest", "truncated", "oversized", "symlink"]
)
def test_real_ram_copy_authenticates_before_publication(tmp_path, failure):
    source = tmp_path / "runtime"
    source.write_bytes(b"authenticated migration runtime")
    expected = boot.digest(source)
    size = source.stat().st_size
    if failure == "digest":
        source.write_bytes(b"x" * size)
    elif failure == "truncated":
        source.write_bytes(b"short")
    elif failure == "oversized":
        source.write_bytes(b"x" * (size + 1))
    elif failure == "symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(source)
        source = alias
    destination = tmp_path / "ram.squashfs"
    result = subprocess.run(
        [
            "bash",
            "-c",
            '. "$1"; copy_migration_payload "$2" "$3" "$4" "$5"',
            "test",
            str(Path("conf/migration-load.sh").resolve()),
            str(source),
            str(destination),
            expected,
            str(size),
        ],
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) == (failure is None)
    assert destination.exists() == (failure is None)
    if failure is None:
        source.unlink()
        assert boot.digest(destination) == expected


@pytest.mark.parametrize(
    "failure",
    [None, "duplicate", "target", "disk-root", "umount", "tamper", "swap", "memory"],
)
def test_loader_orders_identity_copy_authentication_and_detach(tmp_path, failure):
    # Mock only hardware syscalls. The loader, bounded copy and hash run unchanged.
    source = tmp_path / "migration-source/luxnix-migration"
    source.mkdir(parents=True)
    payload = source / "input"
    payload.write_bytes(b"runtime")
    expected = boot.digest(payload)
    size = payload.stat().st_size
    payload = payload.rename(source / (expected + ".squashfs"))
    if failure == "tamper":
        payload.write_bytes(b"garbage")
    script = r"""
        . "$LOADER"
        test() { if [ "$1" = -b ]; then return 0; else builtin test "$@"; fi; }
        findmnt() {
            if [ "$FAILURE" = disk-root ]; then echo ext4; else echo tmpfs; fi
        }
        awk() {
            case "$2" in
                /proc/swaps) if [ "$FAILURE" = swap ]; then echo 2; else echo 1; fi ;;
                /proc/meminfo)
                    if [ "$FAILURE" = memory ]; then echo 0; else echo 1048576; fi ;;
                *) command awk "$@" ;;
            esac
        }
        blkid() {
            echo /dev/recovery
            if [ "$FAILURE" = duplicate ]; then echo /dev/duplicate; fi
            return 0
        }
        lsblk() {
            if [ "$FAILURE" = target ]; then echo 'disk target'
            else echo 'disk external'; fi
        }
        mount() { echo mount >> "$WORK/events"; }
        umount() { echo umount >> "$WORK/events"; [ "$FAILURE" != umount ]; }
        if load_migration_payload "$WORK" 1111-2222 vfat "$HASH" "$SIZE" 1 target; then
            echo start-runtime >> "$WORK/events"
        else exit 1; fi
    """
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "LOADER": str(Path("conf/migration-load.sh").resolve()),
            "WORK": str(tmp_path),
            "FAILURE": failure or "",
            "HASH": expected,
            "SIZE": str(size),
        },
    )
    assert (result.returncode == 0) == (failure is None), result.stderr
    events = (
        (tmp_path / "events").read_text().splitlines()
        if (tmp_path / "events").exists()
        else []
    )
    if failure is None:
        assert events == ["mount", "umount", "start-runtime"]
        assert boot.digest(tmp_path / "nix-store.squashfs") == expected
    else:
        assert "start-runtime" not in events


@pytest.mark.parametrize(
    "mode,allowed", [("local-console", False), ("secure-boot", True)]
)
def test_staging_requires_matching_explicit_boot_trust(
    stage, monkeypatch, spec, mode, allowed
):
    args, variables, calls = stage
    spec["boot_trust"] = mode
    args.allow_unverified_boot = allowed
    args.apply = True
    with pytest.raises(ValueError, match="cannot be downgraded"):
        boot.stage(args)
    assert "LoaderEntryOneShot" not in variables
    assert not (args.esp / "EFI").exists()


def test_console_image_stages_without_signer_but_keeps_payload_check(stage, spec):
    args, variables, calls = stage
    spec["boot_trust"] = "local-console"
    args.allow_unverified_boot = True
    args.apply = True
    boot.stage(args)
    assert "LoaderEntryOneShot" in variables
    assert not any(call[0] == "sbverify" for call in calls)


@pytest.mark.parametrize(
    "console,answer,accepted",
    [
        ("/dev/tty1", "BOOT UNVERIFIED test-host aaaaaaaaaaaa", True),
        ("/dev/tty1", "yes", False),
        ("/dev/pts/0", "BOOT UNVERIFIED test-host aaaaaaaaaaaa", False),
    ],
)
def test_unverified_admission_requires_exact_physical_approval(
    spec, tmp_path, monkeypatch, console, answer, accepted
):
    spec["boot_trust"] = "local-console"
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    monkeypatch.setattr(boot, "require_machine", lambda *a: None)
    monkeypatch.setattr(boot.sb, "run", lambda *a: "tmpfs" if a[0] == "findmnt" else "")
    monkeypatch.setattr(
        boot.sys, "stdin", SimpleNamespace(isatty=lambda: True, fileno=lambda: 0)
    )
    monkeypatch.setattr(boot.os, "ttyname", lambda _: console)
    monkeypatch.setattr("builtins.input", lambda _: answer)
    args = SimpleNamespace(spec=path, certificate=Path("unused"))
    if accepted:
        boot.admit(args)
    else:
        with pytest.raises(ValueError, match="console approval|physical console"):
            boot.admit(args)


def test_console_mode_still_checks_hardware_and_ram(spec, monkeypatch):
    spec["boot_trust"] = "local-console"
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path: spec["hardware_uuid"]
        if path.name == "product_uuid"
        else "MemTotal: 1024 kB\n",
    )
    monkeypatch.setattr(
        boot.sb, "firmware_check", lambda *a: pytest.fail("requires enrollment")
    )
    with pytest.raises(ValueError, match="Insufficient RAM"):
        boot.require_machine(spec, spec["host"], Path("unused"))


def test_build_defaults_to_console_mode_without_signing(monkeypatch):
    selected = []
    monkeypatch.setattr(boot, "build", selected.append)
    boot.main(
        [
            "build",
            "gc-09",
            "--interface",
            "enp4s0",
            "--address",
            "192.0.2.10/24",
            "--controller-cidr",
            "192.0.2.1/32",
            "--recovery-uuid",
            "1111-2222",
            "--recovery-fstype",
            "vfat",
            "--output",
            "/unused",
        ]
    )
    assert selected[0].boot_trust == "local-console"
    assert selected[0].console == "tty1"
    assert selected[0].sign is False
