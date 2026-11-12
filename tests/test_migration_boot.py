"""Boot artifact safety tests; never touch real firmware or storage."""

import contextlib
import copy
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
from types import SimpleNamespace

import pytest

from lx_administration.storage import migration_boot as boot
from lx_administration.yaml import load_unique_yaml_file

RECOVERY_UUID = "11111111-2222-4222-8222-222222222222"


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
        "recovery": {"uuid": RECOVERY_UUID, "fstype": "ext4", "luks_uuid": None},
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
                            "uuid": "11111111-2222-4222-8222-222222222222",
                            "fstype": "ext4",
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


def test_esp_capacity_is_rechecked_under_publication_lock(stage, monkeypatch):
    args, variables, calls = stage
    args.apply = True
    available = iter([2**30, 0])
    monkeypatch.setattr(
        boot.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(
            free=next(available) if path == args.esp else 2**30
        ),
    )
    with pytest.raises(ValueError, match="ESP lacks space"):
        boot.stage(args)
    assert not (args.esp / "EFI").exists()
    assert "LoaderEntryOneShot" not in variables
    assert (
        args.esp / "loader/loader.conf"
    ).read_text() == "default nixos-generation-*\n"


def test_repeated_stage_needs_reserve_without_second_image_copy(stage, monkeypatch):
    args, variables, calls = stage
    args.apply = True
    boot.stage(args)
    retained = {p: p.read_bytes() for p in args.esp.rglob("*") if p.is_file()}
    reserve = (
        load_unique_yaml_file(Path("conf/migration-environment.yml"))["esp_reserve_mib"]
        * boot.MIB
    )
    monkeypatch.setattr(
        boot.shutil, "disk_usage", lambda _: SimpleNamespace(free=reserve)
    )
    boot.stage(args)
    assert retained == {p: p.read_bytes() for p in args.esp.rglob("*") if p.is_file()}


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
            return result.replace(RECOVERY_UUID, "33333333-4444-4444-8444-444444444444")
        return result

    monkeypatch.setattr(boot.sb, "run", run)
    with pytest.raises(ValueError, match="Recovery"):
        boot.stage(args)
    assert "LoaderEntryOneShot" not in variables
    assert not (args.esp / "EFI").exists()


def test_unmounted_recovery_names_the_fix_and_changes_nothing(stage, monkeypatch):
    args, variables, calls = stage
    args.apply = True
    original = boot.sb.run

    def run(*command):
        if command[0] == "findmnt" and args.recovery in command:
            raise boot.sb.SecureBootError("findmnt failed: no error output")
        return original(*command)

    monkeypatch.setattr(boot.sb, "run", run)
    with pytest.raises(ValueError, match="Nothing is mounted at .*setup-media"):
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
        if load_migration_payload "$WORK" "$UUID" btrfs "$HASH" "$SIZE" 1 target; then
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
            "UUID": RECOVERY_UUID,
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
            "11111111-2222-4222-8222-222222222222",
            "--recovery-fstype",
            "ext4",
            "--output",
            "/unused",
        ]
    )
    assert selected[0].boot_trust == "local-console"
    assert selected[0].console == "tty1"
    assert selected[0].sign is False


@pytest.fixture
def discovery(monkeypatch, spec):
    monkeypatch.setattr(boot.socket, "gethostname", lambda: spec["host"])
    import lx_administration.yaml

    monkeypatch.setattr(
        lx_administration.yaml,
        "load_unique_yaml_file",
        lambda _: {"boot_storage": {"hosts": {spec["host"]: spec}}},
    )
    records = {
        "route": [{"dev": "eth0", "gateway": "192.0.2.1"}],
        "address": [
            {"addr_info": [{"scope": "global", "local": "192.0.2.10", "prefixlen": 24}]}
        ],
        "findmnt": {
            "filesystems": [
                {
                    "source": "/dev/sdb1",
                    "uuid": "11111111-2222-4222-8222-222222222222",
                    "fstype": "ext4",
                    "fsroot": "/",
                }
            ]
        },
        "lsblk": {"blockdevices": [{"type": "part", "uuid": RECOVERY_UUID}]},
    }

    def run(*command):
        key = command[3] if command[0] == "ip" else command[0]
        assert key in records, command
        return json.dumps(records[key])

    monkeypatch.setattr(boot.sb, "run", run)
    return records


def test_discovery_yaml_and_printed_command_roundtrip(discovery, capsys, monkeypatch):
    import shlex
    import yaml

    boot.main(["discover", "--controller-cidr", "192.0.2.1/32"])
    settings = yaml.safe_load(capsys.readouterr().out)
    assert settings["host"] == "test-host"
    assert settings["address"] == "192.0.2.10/24"
    assert settings["recovery_uuid"] == "11111111-2222-4222-8222-222222222222"
    selected = []
    monkeypatch.setattr(boot, "build", selected.append)
    boot.main(
        [
            "discover",
            "--controller-cidr",
            "192.0.2.1/32",
            "--format",
            "command",
            "--output",
            "/home/admin/a directory",
        ]
    )
    command = shlex.split(capsys.readouterr().out)
    assert command[:3] == ["devenv", "shell", "migration-boot"]
    boot.main(command[3:])
    for field in boot.BUILD_SETTINGS:
        assert getattr(selected[0], field) == settings[field]
    assert selected[0].output == Path("/home/admin/a directory")


@pytest.mark.parametrize(
    "failure", ["host", "routes", "addresses", "mount", "encryption"]
)
def test_discovery_rejects_ambiguous_or_foreign_inputs(discovery, failure):
    args = ["discover"]
    if failure == "host":
        args.append("another-host")
    elif failure == "routes":
        discovery["route"] *= 2
    elif failure == "addresses":
        discovery["address"][0]["addr_info"] *= 2
    elif failure == "mount":
        discovery["findmnt"]["filesystems"] = []
    else:
        discovery["lsblk"]["blockdevices"] = [{"type": "crypt"}]
    with pytest.raises(SystemExit) as error:
        boot.main(args)
    assert error.value.code == 1


def test_discovery_recognizes_encrypted_media(discovery, capsys):
    import yaml

    discovery["lsblk"]["blockdevices"] = [
        {
            "type": "crypt",
            "children": [
                {"type": "part", "fstype": "crypto_LUKS", "uuid": "outer-uuid"}
            ],
        }
    ]
    boot.main(["discover"])
    settings = yaml.safe_load(capsys.readouterr().out)
    assert settings["recovery_luks_uuid"] == "outer-uuid"
    assert settings["controller_cidr"] is None


@pytest.mark.parametrize(
    "failure", [None, "host", "uuid", "unknown", "missing", "type"]
)
def test_build_settings_bound_to_host_with_explicit_overrides(tmp_path, spec, failure):
    import yaml

    values = {
        "host": spec["host"],
        "hardware_uuid": spec["hardware_uuid"],
        "interface": "eth0",
        "address": "192.0.2.10/24",
        "gateway": None,
        "controller_cidr": "192.0.2.1/32",
        "recovery_uuid": "11111111-2222-4222-8222-222222222222",
        "recovery_fstype": "ext4",
        "recovery_luks_uuid": None,
    }
    if failure == "host":
        values["host"] = "other-host"
    elif failure == "uuid":
        values["hardware_uuid"] = "wrong"
    elif failure == "unknown":
        values["sign"] = True
    elif failure == "missing":
        values["controller_cidr"] = None
    elif failure == "type":
        values["interface"] = ["eth0"]
    path = tmp_path / "settings.yml"
    path.write_text(yaml.safe_dump(values))
    args = SimpleNamespace(
        host=spec["host"],
        settings=path,
        **{name: None for name in boot.BUILD_SETTINGS},
    )
    args.address = "192.0.2.20/24"
    if failure:
        with pytest.raises(ValueError):
            boot.build_settings(args, spec)
    else:
        boot.build_settings(args, spec)
        assert args.address == "192.0.2.20/24"
        assert args.interface == "eth0"


@pytest.mark.parametrize(
    "keys,accepted",
    [
        ([], True),
        (["not-a-public-key"], False),
        (None, False),
        (["ssh-ed25519 AAAA test-fixture\nextra"], False),
    ],
)
def test_local_console_accepts_no_keys_but_rejects_malformed_keys(spec, keys, accepted):
    spec.update(boot_trust="local-console", authorized_keys=keys)
    if accepted:
        boot.validate_spec(spec)
    else:
        with pytest.raises(ValueError, match="public keys"):
            boot.validate_spec(spec)


@pytest.mark.parametrize("keyless", [True, False])
def test_console_ssh_units_follow_administrator_keys(spec, keyless):
    spec["boot_trust"] = "local-console"
    if keyless:
        spec["authorized_keys"] = []
    root = Path.cwd()
    expression = (
        f"let f = builtins.getFlake {json.dumps('git+file://' + str(root))}; "
        f"c = (import {root}/conf/migration-environment.nix {{inputs=f.inputs; "
        f"spec=builtins.fromJSON {json.dumps(json.dumps(spec))};}}).config; "
        "in { ssh = c.services.openssh.enable; "
        "daemon = c.systemd.services ? sshd; "
        "admission = c.systemd.services.luxnix-migration-admission.requires; "
        "firewall = c.networking.firewall.extraCommands; "
        "generator = c.systemd.generators.systemd-ssh-generator or null; "
        "console = c.systemd.services ? luxnix-migration-console; }"
    )
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    config = json.loads(result.stdout)
    assert config["console"]
    assert config["ssh"] == config["daemon"] == (not keyless)
    assert ("sshd-keygen.service" in config["admission"]) == (not keyless)
    assert ("--dport 2222" in config["firewall"]) == (not keyless)
    assert (config["generator"] == "/dev/null") == keyless


@pytest.mark.parametrize(
    "key",
    [
        'from="172.16.255.22",restrict ssh-ed25519 AAAA restricted',
        'command="echo \\"hello world\\"",no-pty ssh-ed25519 AAAA command',
        "ssh-ed25519 AAAA user's key",
        "sk-ssh-ed25519@openssh.com AAAA security-key",
        "sk-ecdsa-sha2-nistp256@openssh.com AAAA security-key",
    ],
)
def test_authorized_key_options_and_comments_are_preserved(spec, key):
    spec["authorized_keys"] = [key]
    boot.validate_spec(spec)
    assert spec["authorized_keys"] == [key]


@pytest.mark.parametrize(
    "key",
    [
        'from="unclosed ssh-ed25519 AAAA',
        "ssh-ed25519",
        "ssh-ed25519 !!!!",
        'from="172.16.255.22",restrict invalid-key AAAA',
        "ssh-ed25519 AAAA\rssh-ed25519 BBBB",
        "ssh-ed25519 AAAA\nssh-ed25519 BBBB",
    ],
)
def test_malformed_authorized_key_lines_are_rejected(spec, key):
    spec["authorized_keys"] = [key]
    with pytest.raises(ValueError, match="public keys"):
        boot.validate_spec(spec)


@pytest.fixture
def local_bundle(stage, monkeypatch):
    args, variables, calls = stage
    bundle = args.image.parent / f"migration-{args.host}"
    bundle.mkdir()
    (bundle / "migration.efi").write_bytes(args.image.read_bytes())
    (bundle / "migration.squashfs").write_bytes(args.payload.read_bytes())
    args.certificate.write_text("public test certificate")
    monkeypatch.setattr(Path, "home", lambda: bundle.parent)
    monkeypatch.setattr(boot.socket, "gethostname", lambda: args.host)
    command = [
        "stage",
        "--certificate",
        str(args.certificate),
        "--recovery",
        str(args.recovery),
        "--esp",
        str(args.esp),
    ]
    return command, bundle, args, variables, calls


@pytest.mark.parametrize("apply", [False, True])
def test_short_stage_discovers_bundle_and_reuses_existing_guards(local_bundle, apply):
    command, bundle, args, variables, calls = local_bundle
    boot.main(command + (["--apply"] if apply else []))
    assert ("LoaderEntryOneShot" in variables) == apply
    assert not any("set-default" in call or "reboot" in call for call in calls)


@pytest.mark.parametrize(
    "missing", ["migration.efi", "migration.squashfs", "certificate", "recovery", "esp"]
)
def test_short_stage_missing_inputs_fail_before_sudo(
    local_bundle, monkeypatch, missing
):
    command, bundle, args, variables, calls = local_bundle
    if missing in {"recovery", "esp"}:
        command[command.index("--" + missing) + 1] += "/missing"
    else:
        (args.certificate if missing == "certificate" else bundle / missing).unlink()
    monkeypatch.setattr(boot.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(
        boot.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("must not request sudo"),
    )
    with pytest.raises(SystemExit) as error:
        boot.main(command + ["--apply"])
    assert error.value.code == 1
    assert not calls


def test_short_stage_pins_user_paths_and_digest_across_sudo(local_bundle, monkeypatch):
    command, bundle, args, variables, calls = local_bundle
    invoked = []
    monkeypatch.setattr(boot.os, "geteuid", lambda: 1000)

    def elevate(argv, **kwargs):
        invoked.append(argv)
        assert argv[:3] == ["sudo", "--", "env"]
        assert "uv" not in argv
        assert argv[argv.index("--image") + 1] == str(bundle / "migration.efi")
        assert argv[argv.index("--sha256") + 1] == boot.digest(bundle / "migration.efi")
        monkeypatch.setattr(boot.os, "geteuid", lambda: 0)
        boot.main(argv[argv.index("lx_administration.storage.migration_boot") + 1 :])

    monkeypatch.setattr(boot.subprocess, "run", elevate)
    boot.main(command + ["--apply"])
    assert len(invoked) == 1
    assert "LoaderEntryOneShot" in variables


def test_short_stage_rejects_mixed_or_partial_artifact_inputs(local_bundle):
    command, bundle, args, variables, calls = local_bundle
    for extra in (
        ["--image", str(args.image)],
        [
            "--bundle",
            str(bundle),
            "--image",
            str(args.image),
            "--payload",
            str(args.payload),
            "--sha256",
            args.sha256,
        ],
    ):
        with pytest.raises(SystemExit):
            boot.main(command + extra)
    assert not calls


def test_short_stage_tampered_payload_cannot_arm_boot(local_bundle):
    command, bundle, args, variables, calls = local_bundle
    (bundle / "migration.squashfs").write_bytes(b"tampered")
    with pytest.raises(SystemExit):
        boot.main(command + ["--apply"])
    assert "LoaderEntryOneShot" not in variables


@pytest.fixture
def firmware(monkeypatch):
    """A fake systemd-boot variable store; bootctl writes go only here."""
    variables = {}
    calls = []
    verbs = {"set-default": "LoaderEntryDefault", "set-oneshot": "LoaderEntryOneShot"}

    def run(*args, **kwargs):
        calls.append(args)
        assert args[0] == "bootctl" and args[1] in verbs
        if args[2]:
            variables[verbs[args[1]]] = args[2]
        else:
            variables.pop(verbs[args[1]], None)
        return ""

    monkeypatch.setattr(boot, "loader_variable", variables.get)
    monkeypatch.setattr(boot.sb, "run", run)
    return variables, calls


MIGRATION_ENTRY = "luxnix-migration-gc-09-67372ff722c24ad6.conf"


def test_hold_points_every_reboot_at_the_booted_migration_entry(firmware):
    variables, calls = firmware
    variables.update(
        LoaderEntrySelected=MIGRATION_ENTRY,
        LoaderEntryDefault="nixos-generation-25.conf",
    )
    hold = boot.hold_for_migration("gc-09")
    assert hold == {
        "held": True,
        "previous": "nixos-generation-25.conf",
        "entry": MIGRATION_ENTRY,
    }
    assert variables["LoaderEntryDefault"] == MIGRATION_ENTRY
    boot.release_hold(hold)
    assert variables["LoaderEntryDefault"] == "nixos-generation-25.conf"
    boot.release_hold(dict(hold, previous=None))
    assert "LoaderEntryDefault" not in variables


@pytest.mark.parametrize(
    "selected",
    [None, "nixos-generation-25.conf", "luxnix-migration-gc-10-67372ff722c24ad6.conf"],
)
def test_hold_never_redirects_boot_outside_this_hosts_migration_entry(
    firmware, selected
):
    variables, calls = firmware
    if selected:
        variables["LoaderEntrySelected"] = selected
    hold = boot.hold_for_migration("gc-09")
    assert hold["held"] is False
    boot.release_hold(hold)
    assert calls == []


def test_unreadable_hold_is_an_error(firmware, monkeypatch):
    variables, _ = firmware
    variables["LoaderEntrySelected"] = MIGRATION_ENTRY
    monkeypatch.setattr(boot.sb, "run", lambda *a, **k: "")
    with pytest.raises(ValueError, match="did not read back"):
        boot.hold_for_migration("gc-09")


CLOSURE = "/nix/store/" + "c" * 32 + "-nixos-system-gc-09"


@pytest.fixture
def installed(tmp_path):
    root, esp = tmp_path / "mnt", tmp_path / "mnt/boot"
    profiles = root / "nix/var/nix/profiles"
    profiles.mkdir(parents=True)
    (profiles / "system").symlink_to("system-38-link")
    (esp / "loader/entries").mkdir(parents=True)
    (esp / "EFI/nixos").mkdir(parents=True)
    for name in ("kernel.efi", "initrd.efi"):
        (esp / "EFI/nixos" / name).write_text("test")
    entry = esp / "loader/entries/nixos-generation-38.conf"
    entry.write_text(
        "linux /EFI/nixos/kernel.efi\ninitrd /EFI/nixos/initrd.efi\n"
        f"options init={CLOSURE}/init root=/dev/mapper/cryptroot\n"
    )
    (esp / "loader/loader.conf").write_text(
        "timeout 5\ndefault nixos-generation-38.conf\n"
    )
    return root, esp, entry


def test_handover_clears_overrides_so_loader_conf_boots_the_new_system(
    firmware, installed
):
    variables, _ = firmware
    root, esp, _ = installed
    variables.update(
        LoaderEntryDefault=MIGRATION_ENTRY,
        LoaderEntryOneShot="nixos-generation-25.conf",
    )
    assert boot.hand_over_boot(root, esp, CLOSURE) == "nixos-generation-38.conf"
    # A pinned EFI default would also freeze out every later rebuild.
    assert "LoaderEntryDefault" not in variables
    assert "LoaderEntryOneShot" not in variables


def test_handover_refuses_an_entry_for_another_closure(firmware, installed):
    variables, calls = firmware
    root, esp, entry = installed
    variables["LoaderEntryDefault"] = MIGRATION_ENTRY
    entry.write_text(entry.read_text().replace("c" * 32, "d" * 32))
    with pytest.raises(ValueError, match="does not boot the planned closure"):
        boot.hand_over_boot(root, esp, CLOSURE)
    assert variables["LoaderEntryDefault"] == MIGRATION_ENTRY and calls == []


def test_handover_refuses_a_loader_conf_default_elsewhere(firmware, installed):
    variables, _ = firmware
    root, esp, _ = installed
    (esp / "loader/loader.conf").write_text("default nixos-generation-25.conf\n")
    with pytest.raises(ValueError, match="not the installed nixos-generation-38"):
        boot.hand_over_boot(root, esp, CLOSURE)


def parse_newc(archive: bytes) -> dict:
    """Independent reader for the archive the kernel unpacks."""
    entries, offset = {}, 0
    while True:
        assert archive[offset : offset + 6] == b"070701"
        header = archive[offset + 6 : offset + 110]
        fields = [int(header[8 * i : 8 * i + 8], 16) for i in range(13)]
        size, name_size, mode = fields[6], fields[11], fields[1]
        name_start = offset + 110
        name = archive[name_start : name_start + name_size - 1].decode()
        data_start = name_start + name_size + (-(110 + name_size) % 4)
        data = archive[data_start : data_start + size]
        offset = data_start + size + (-size % 4)
        if name == "TRAILER!!!":
            assert offset == len(archive)
            return entries
        entries[name] = (mode, data)


def test_kexec_archive_is_a_valid_newc_archive():
    archive = boot.newc(
        [
            ("luxnix-kexec", 0o040700, None),
            ("luxnix-kexec/key", 0o100600, b"private"),
            ("luxnix-kexec/odd", 0o100644, b"abcde"),
        ]
    )
    assert len(archive) % 4 == 0
    assert parse_newc(archive) == {
        "luxnix-kexec": (0o040700, b""),
        "luxnix-kexec/key": (0o100600, b"private"),
        "luxnix-kexec/odd": (0o100644, b"abcde"),
    }


@pytest.fixture
def kexec_identity(tmp_path, monkeypatch, spec):
    run = tmp_path / "run"
    run.mkdir()
    key = run / "ssh_host_ed25519_key"
    key.write_text("private")
    key.chmod(0o600)
    public = "ssh-ed25519 AAAAkey target-migration"
    (run / "ssh_host_ed25519_key.pub").write_text(public + "\n")
    (run / "identity.json").write_text(
        json.dumps(
            {
                "host": spec["host"],
                "revision": spec["revision"],
                "public_key": "ssh-ed25519 AAAAkey target-migration",
            }
        )
    )
    monkeypatch.setattr(boot, "KEXEC_RUN", run)
    real = Path.lstat
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda p: os.stat_result([*list(real(p))[:4], 0, *list(real(p))[5:]])
        if p == key
        else real(p),
    )
    return run


def test_kexec_admission_accepts_only_the_pinned_host_key(kexec_identity, spec):
    spec = spec | {"boot_trust": "host-kexec"}
    boot.require_kexec_identity(spec)
    (kexec_identity / "ssh_host_ed25519_key.pub").write_text("ssh-ed25519 AAAAother\n")
    with pytest.raises(ValueError, match="differs from the pinned one"):
        boot.require_kexec_identity(spec)


def test_kexec_admission_refuses_without_a_handed_over_key(kexec_identity, spec):
    (kexec_identity / "identity.json").unlink()
    with pytest.raises(ValueError, match="SSH stays closed"):
        boot.require_kexec_identity(spec | {"boot_trust": "host-kexec"})


def test_host_kexec_specs_require_administrator_keys(spec):
    boot.validate_spec(spec | {"boot_trust": "host-kexec"})
    with pytest.raises(ValueError, match="administrator public keys"):
        boot.validate_spec(spec | {"boot_trust": "host-kexec", "authorized_keys": []})


@pytest.fixture
def kexec_host(tmp_path, monkeypatch, spec):
    """A target with a prebuilt bundle; records every privileged command."""
    spec = spec | {"boot_trust": "host-kexec"}
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "kernel").write_bytes(b"k" * 100)
    (bundle / "initrd").write_bytes(b"i" * 103)
    (bundle / "cmdline").write_text("init=/nix/store/x/init console=tty0")
    (bundle / "manifest.json").write_text(json.dumps(spec))
    net = tmp_path / "net" / spec["interface"]
    net.mkdir(parents=True)
    (net / "addr_assign_type").write_text("0\n")
    (net / "address").write_text("52:54:00:12:01:02\n")
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 16000000 kB\nMemAvailable: 8000000 kB\n")

    @contextlib.contextmanager
    def private_workspace():
        yield workspace

    def run(*args, **kwargs):
        if args[:2] == ("ssh-keygen", "-q"):
            key = Path(args[-1])
            key.write_text("private")
            key.with_suffix(".pub").write_text("ssh-ed25519 AAAAkey target-migration\n")
            return ""
        if args[:2] == ("ssh-keygen", "-lf"):
            return "256 SHA256:pinned target-migration (ED25519)\n"
        raise AssertionError(args)

    calls = []
    monkeypatch.setattr(boot.socket, "gethostname", lambda: spec["host"])
    monkeypatch.setattr(boot, "require_machine", lambda *a: None)
    monkeypatch.setattr(boot, "NETWORK", tmp_path / "net")
    monkeypatch.setattr(boot, "LOCKDOWN", tmp_path / "lockdown")
    arp = tmp_path / "arp"
    arp.write_text(
        "IP address HW type Flags HW address Mask Device\n"
        f"192.0.2.1 0x1 0x2 52:54:00:12:01:01 * {spec['interface']}\n"
    )
    monkeypatch.setattr(boot, "ARP", arp)
    monkeypatch.setattr(boot.time, "sleep", lambda s: None)
    monkeypatch.setattr(boot.sb, "private_workspace", private_workspace)
    monkeypatch.setattr(boot.sb, "run", run)
    monkeypatch.setattr(boot.sb, "_require_tty", lambda: None)
    monkeypatch.setattr(boot, "as_root", lambda *c: calls.append(c))
    real_read = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda p, *a, **k: real_read(
            meminfo if str(p) == "/proc/meminfo" else p, *a, **k
        ),
    )
    args = SimpleNamespace(
        host=None, bundle=bundle, output=tmp_path / "out", apply=False, flake=None
    )
    return args, calls, workspace, spec


def test_kexec_preview_pins_the_key_and_loads_nothing(kexec_host, capsys):
    args, calls, workspace, spec = kexec_host
    boot.kexec(args)
    out = capsys.readouterr().out
    assert "Host key: 256 SHA256:pinned" in out and "Preview only" in out
    assert calls == []
    known = (args.output / "known_hosts").read_text()
    assert known == "[192.0.2.10]:2222 ssh-ed25519 AAAAkey\n"
    # The appended archive carries the key, its identity and the interface rule.
    initrd = (workspace / "initrd").read_bytes()
    assert initrd.startswith(b"i" * 103)
    entries = parse_newc(initrd[104:])
    assert entries["luxnix-kexec/ssh_host_ed25519_key"] == (0o100600, b"private")
    identity = json.loads(entries["luxnix-kexec/identity.json"][1])
    assert identity == {
        "host": spec["host"],
        "revision": spec["revision"],
        "public_key": "ssh-ed25519 AAAAkey target-migration",
    }
    link = entries["luxnix-kexec/10-luxnix-management.link"][1].decode()
    assert "PermanentMACAddress=52:54:00:12:01:02" in link and "Name=eth0" in link


def test_kexec_apply_loads_then_switches_after_the_typed_phrase(
    kexec_host, monkeypatch
):
    args, calls, workspace, spec = kexec_host
    args.apply = True
    monkeypatch.setattr("builtins.input", lambda prompt: f"START RAM {spec['host']}")
    boot.kexec(args)
    assert calls[0][:3] == ("kexec", "--load", str(args.bundle / "kernel"))
    assert calls[0][3:5] == ("--initrd", str(workspace / "initrd"))
    assert calls[0][-1] == "init=/nix/store/x/init console=tty0"
    assert calls[1] == ("systemctl", "kexec")


def test_kexec_apply_without_the_phrase_loads_nothing(kexec_host, monkeypatch):
    args, calls, _, _ = kexec_host
    args.apply = True
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    with pytest.raises(ValueError, match="nothing was loaded"):
        boot.kexec(args)
    assert calls == []


def test_kexec_refuses_under_kernel_lockdown(kexec_host, tmp_path):
    args, calls, _, _ = kexec_host
    (tmp_path / "lockdown").write_text("none [integrity] confidentiality\n")
    with pytest.raises(ValueError, match="lockdown"):
        boot.kexec(args)
    assert calls == []


def test_kexec_refuses_a_changed_hardware_address(kexec_host, tmp_path, spec):
    args, calls, _, _ = kexec_host
    (tmp_path / "net" / spec["interface"] / "addr_assign_type").write_text("3\n")
    with pytest.raises(ValueError, match="changed hardware address"):
        boot.kexec(args)


def test_kexec_runs_only_on_its_own_host(kexec_host):
    args, calls, _, _ = kexec_host
    args.host = "another-host"
    with pytest.raises(ValueError, match="target host itself"):
        boot.kexec(args)


@pytest.mark.parametrize(
    "arp_line",
    [
        "",  # Nobody ever answered.
        "192.0.2.1 0x1 0x0 00:00:00:00:00:00 * eth0",
        "192.0.2.1 0x1 0x2 52:54:00:12:01:01 * wlan0",
    ],
)
def test_kexec_refuses_when_the_controller_is_absent(
    kexec_host, tmp_path, monkeypatch, arp_line
):
    args, calls, _, _ = kexec_host
    args.apply = True
    header = "IP address HW type Flags HW address Mask Device\n"
    (tmp_path / "arp").write_text(header + arp_line)
    monkeypatch.setattr(boot.socket.socket, "sendto", lambda *a: 0)
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("asked"))
    with pytest.raises(ValueError, match="No controller answers at 192.0.2.1 on eth0"):
        boot.kexec(args)
    assert calls == []
    assert not (args.output / "known_hosts").exists()


def test_kexec_off_subnet_controller_needs_a_present_gateway(kexec_host, monkeypatch):
    args, calls, _, spec = kexec_host
    monkeypatch.setattr(boot.socket.socket, "sendto", lambda *a: 0)
    remote = spec | {"controller_cidr": "198.51.100.7/32"}
    with pytest.raises(ValueError, match="outside 192.0.2.0/24 and no gateway"):
        boot.require_controller_link(remote)
    with pytest.raises(ValueError, match="No gateway answers at 192.0.2.254"):
        boot.require_controller_link(remote | {"gateway": "192.0.2.254"})
    boot.require_controller_link(remote | {"gateway": "192.0.2.1"})


@pytest.fixture
def settings_host(tmp_path, monkeypatch):
    state = tmp_path / "luxnix-state" / "gc-09"
    state.mkdir(parents=True)
    observed = {
        "host": "gc-09",
        "hardware_uuid": "e0118e2d-e0c4-9844-a4eb-9fe2b5747b0d",
        "interface": "enp4s0",
        "address": "192.168.0.222/24",
        "gateway": "192.168.0.1",
        "controller_cidr": None,
        "recovery_uuid": "530b7f22-bb3d-4444-8966-f6802e590f50",
        "recovery_fstype": "ext4",
        "recovery_luks_uuid": None,
    }
    monkeypatch.setattr(boot, "plan_settings", lambda host: state / boot.SETTINGS_FILE)
    monkeypatch.setattr(
        boot, "observe_settings", lambda args, host, cfg: dict(observed)
    )
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    args = SimpleNamespace(host="gc-09", controller_cidr=None, settings=None)
    return state, args


def test_settings_are_discovered_and_saved_with_the_plan(settings_host, monkeypatch):
    state, args = settings_host
    monkeypatch.setenv("SSH_CONNECTION", "192.168.0.201 50000 192.168.0.222 22")
    path = boot.default_settings(args, {})
    assert path == state / boot.SETTINGS_FILE
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    saved = load_unique_yaml_file(path)
    assert saved["controller_cidr"] == "192.168.0.201/32"
    assert set(saved) == {"host", "hardware_uuid", *boot.BUILD_SETTINGS}
    # A later run reuses the saved file instead of discovering again.
    monkeypatch.setattr(
        boot, "observe_settings", lambda *a: pytest.fail("reuse the saved file")
    )
    assert boot.default_settings(args, {}) == path


def test_a_vpn_session_is_never_taken_as_the_controller(settings_host, monkeypatch):
    state, args = settings_host
    monkeypatch.setenv("SSH_CONNECTION", "172.16.255.10 50000 172.16.255.109 22")
    with pytest.raises(ValueError, match="outside the management network"):
        boot.default_settings(args, {})
    assert not (state / boot.SETTINGS_FILE).exists()


def test_an_explicit_controller_is_kept(settings_host, monkeypatch):
    state, args = settings_host
    monkeypatch.setenv("SSH_CONNECTION", "172.16.255.10 50000 172.16.255.109 22")

    def observe(args, host, cfg):
        return {"controller_cidr": args.controller_cidr, "address": "192.168.0.222/24"}

    monkeypatch.setattr(boot, "observe_settings", observe)
    args.controller_cidr = "192.168.0.201/32"
    path = boot.default_settings(args, {})
    assert load_unique_yaml_file(path)["controller_cidr"] == "192.168.0.201/32"


def test_an_empty_settings_file_says_so(tmp_path):
    empty = tmp_path / "migration-settings.yml"
    empty.write_text("")
    args = SimpleNamespace(settings=empty, host="gc-09")
    with pytest.raises(ValueError, match="is empty. Rerun without --settings"):
        boot.build_settings(args, {"hardware_uuid": "x"})


def test_a_stale_settings_file_names_its_keys(tmp_path):
    stale = tmp_path / "migration-settings.yml"
    stale.write_text("host: gc-09\nhardware_uuid: x\nold_key: y\n")
    args = SimpleNamespace(settings=stale, host="gc-09")
    with pytest.raises(ValueError, match=r"unexpected \['old_key'\]"):
        boot.build_settings(args, {"hardware_uuid": "x"})


def test_the_hardware_uuid_is_read_through_sudo_for_an_operator(monkeypatch):
    calls = []

    def denied(path, *a, **k):
        raise PermissionError(path)

    monkeypatch.setattr(Path, "read_text", denied)
    monkeypatch.setattr(boot, "store_tool", lambda name: f"/nix/store/x/bin/{name}")
    monkeypatch.setattr(
        boot.subprocess,
        "run",
        lambda argv, **kw: calls.append(argv)
        or SimpleNamespace(stdout="E0118E2D-E0C4-9844-A4EB-9FE2B5747B0D\n"),
    )
    assert boot.hardware_uuid() == "e0118e2d-e0c4-9844-a4eb-9fe2b5747b0d"
    assert calls == [
        ["sudo", "--", "/nix/store/x/bin/cat", "/sys/class/dmi/id/product_uuid"]
    ]


def test_store_tool_executes_the_multicall_command(tmp_path):
    if not os.path.realpath(shutil.which("cat") or "").startswith("/nix/store/"):
        pytest.skip("requires Nix-store coreutils")
    sample = tmp_path / "sample"
    sample.write_text("public test data\n")
    executable = boot.store_tool("cat")
    assert (
        subprocess.check_output([executable, str(sample)], text=True)
        == sample.read_text()
    )


def test_store_tool_refuses_a_mutable_alias_to_a_store_binary(tmp_path, monkeypatch):
    real = shutil.which("cat")
    if not real or not os.path.realpath(real).startswith("/nix/store/"):
        pytest.skip("requires Nix-store coreutils")
    alias = tmp_path / "cat"
    alias.symlink_to(real)
    monkeypatch.setattr(boot.shutil, "which", lambda name: str(alias))
    with pytest.raises(ValueError, match="from the Nix store is required"):
        boot.store_tool("cat")


@pytest.mark.parametrize("fstype", ["ext4", "btrfs", "vfat", "xfs", "nfs"])
def test_recovery_filesystems_agree_everywhere(spec, fstype):
    """Planning, the RAM build and the loader accept the same recovery drives."""
    from lx_administration.storage import recovery_media

    supported = fstype in ("ext4", "btrfs")
    assert (fstype in recovery_media.FILESYSTEMS) == supported
    spec["recovery"]["fstype"] = fstype
    if supported:
        boot.validate_spec(spec)
    else:
        with pytest.raises(ValueError, match="ext4 or Btrfs"):
            boot.validate_spec(spec)
    loader = Path("conf/migration-load.sh").read_text()
    assert (f"\n        {fstype}) options=ro," in loader) == supported
    environment = Path("conf/migration-environment.nix").read_text()
    if supported:
        assert f'"{fstype}"' in environment.split("supportedFilesystems", 1)[1]
