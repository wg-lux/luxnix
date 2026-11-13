"""Build RAM recovery images and stage an explicit one-shot boot.

No command in this module encrypts storage, enrolls firmware keys or reboots.
The target-side commands use only the standard library and secure_boot.py.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid

from lx_administration import secure_boot as sb

# The recovery drive holds private migration state (POSIX permissions, so no FAT)
# and is mounted by the loader initrd and the RAM environment.
RECOVERY_FILESYSTEMS = ("ext4", "btrfs")

MIB = 1024 * 1024
LOADER_GUID = "4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


RECOVERY_MOUNT_FIX = (
    "mount the recovery drive at its filesystem root first, for example "
    "`devenv shell boot-storage-setup setup-media --apply` "
    "(see docs/migration-environment.md, section 1)"
)


def mounted_filesystems(path: Path, columns: str, fix: str) -> list[dict]:
    """Return findmnt rows for a mountpoint; an empty mountpoint is a clear error."""
    try:
        output = sb.run("findmnt", "--json", "--mountpoint", path, "--output", columns)
    except sb.SecureBootError:
        # findmnt exits 1 without diagnostics when nothing is mounted there.
        if not os.path.ismount(path):
            raise ValueError(f"Nothing is mounted at {path}; {fix}") from None
        raise
    return json.loads(output)["filesystems"]


def authorized_key_line(key) -> bool:
    """Recognize an OpenSSH key line without removing its access restrictions."""
    if not isinstance(key, str) or "\n" in key or "\r" in key:
        return False
    tokens = shlex.shlex(key, posix=True)
    tokens.whitespace_split = True
    tokens.commenters = ""
    key_type = re.compile(
        r"(ssh-(rsa|ed25519)|ecdsa-sha2-nistp(256|384|521)|"
        r"sk-(ssh-ed25519|ecdsa-sha2-nistp256)@openssh\.com)"
    )
    try:
        kind = next(tokens)
        if not key_type.fullmatch(kind):
            kind = next(tokens)  # Optional comma-separated authorized_keys options.
        return bool(
            key_type.fullmatch(kind)
            and re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", next(tokens))
        )
    except (StopIteration, ValueError):
        return False


def validate_spec(spec: dict) -> None:
    if set(spec) - {"payload", "boot_trust", "console"} != {
        "host",
        "hardware_uuid",
        "revision",
        "interface",
        "address",
        "gateway",
        "controller_cidr",
        "authorized_keys",
        "policy",
        "recovery",
        "target_serials",
    }:
        raise ValueError("Unexpected migration image specification fields")
    if spec.get("boot_trust", "secure-boot") not in {
        "secure-boot",
        "local-console",
        "host-kexec",
    }:
        raise ValueError("Unsupported boot trust mode")
    if spec.get("console", "tty1") not in {"tty1", "ttyS0"}:
        raise ValueError("Select a physical console")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", spec["host"]):
        raise ValueError("Invalid inventory hostname")
    if not re.fullmatch(r"[0-9a-f]{40}", spec["revision"]):
        raise ValueError("Image needs an exact reviewed Git revision")
    if str(uuid.UUID(spec["hardware_uuid"])) != spec["hardware_uuid"]:
        raise ValueError("Hardware UUID must use canonical lowercase spelling")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", spec["interface"]):
        raise ValueError("Select the exact management interface")
    address = ipaddress.IPv4Interface(spec["address"])
    controller = ipaddress.IPv4Network(spec["controller_cidr"], strict=True)
    if controller.prefixlen == 0:
        raise ValueError("Do not expose recovery SSH to all addresses")
    if spec["gateway"] is not None:
        gateway = ipaddress.IPv4Address(spec["gateway"])
        if gateway not in address.network:
            raise ValueError("Management gateway must be on the selected subnet")
    keys = spec["authorized_keys"]
    if (
        not isinstance(keys, list)
        or (not keys and spec.get("boot_trust", "secure-boot") != "local-console")
        or any(not authorized_key_line(key) for key in keys)
    ):
        raise ValueError("Image requires explicit inventory administrator public keys")
    recovery = spec["recovery"]
    if set(recovery) != {"uuid", "fstype", "luks_uuid"}:
        raise ValueError("Unexpected recovery filesystem specification")
    if recovery["fstype"] not in RECOVERY_FILESYSTEMS:
        raise ValueError("Recovery filesystem must be ext4 or Btrfs")
    uuid.UUID(recovery["uuid"])
    if recovery["luks_uuid"] is not None:
        uuid.UUID(recovery["luks_uuid"])
    if not spec["target_serials"] or any(
        not re.fullmatch(r"[A-Za-z0-9_.:-]+", serial)
        for serial in spec["target_serials"]
    ):
        raise ValueError("Every target disk requires an unambiguous serial")
    policy = spec["policy"]
    if (
        set(policy)
        != {
            "schema_version",
            "ssh_port",
            "minimum_memory_mib",
            "maximum_image_mib",
            "esp_reserve_mib",
            "maximum_payload_mib",
        }
        or policy["schema_version"] != 2
    ):
        raise ValueError("Unsupported migration environment policy")
    if any(type(value) is not int or value <= 0 for value in policy.values()):
        raise ValueError("Migration limits must be positive integers")
    if not 1024 <= policy["ssh_port"] <= 65535:
        raise ValueError("Recovery SSH requires a distinct unprivileged port")

    if "payload" in spec:
        payload = spec["payload"]
        if set(payload) != {"sha256", "size"} or not re.fullmatch(
            r"[0-9a-f]{64}", payload["sha256"]
        ):
            raise ValueError("Invalid signed payload identity")
        if type(payload["size"]) is not int or not (
            0 < payload["size"] <= policy["maximum_payload_mib"] * MIB
        ):
            raise ValueError("Payload exceeds the signed RAM budget")


def verify_payload(path: Path, spec: dict) -> None:
    payload = spec["payload"]
    if path.is_symlink() or not path.is_file():
        raise ValueError("Payload must be a regular nonsymlinked file")
    if path.stat().st_size != payload["size"] or digest(path) != payload["sha256"]:
        raise ValueError(
            "Payload differs from the digest and size signed into the loader"
        )


def require_recovery(path: Path, spec: dict) -> None:
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("Recovery must be an absolute nonsymlinked mountpoint")
    mounts = mounted_filesystems(path, "SOURCE,UUID,FSTYPE,FSROOT", RECOVERY_MOUNT_FIX)
    expected = spec["recovery"]
    if len(mounts) != 1 or any(
        mounts[0].get(k) != v
        for k, v in {
            "uuid": expected["uuid"],
            "fstype": expected["fstype"],
            "fsroot": "/",
        }.items()
    ):
        raise ValueError("Recovery mount differs from the signed filesystem identity")
    source = mounts[0]["source"]
    if not source.startswith("/dev/"):
        raise ValueError("Recovery must be a local block filesystem")
    devices = sb.run(
        "blkid", "-t", f"UUID={expected['uuid']}", "-o", "device"
    ).splitlines()
    if len(devices) != 1 or Path(devices[0]).resolve() != Path(source).resolve():
        raise ValueError("Recovery filesystem UUID is missing or ambiguous")
    rows = json.loads(
        sb.run(
            "lsblk",
            "--json",
            "--inverse",
            "--paths",
            "--output",
            "NAME,TYPE,SERIAL,UUID",
            source,
        )
    )["blockdevices"]

    nodes = list(block_nodes(rows))
    disks = [n.get("serial") for n in nodes if n["type"] == "disk"]
    if not disks or any(
        not serial or serial in spec["target_serials"] for serial in disks
    ):
        raise ValueError(
            "Recovery is on a target disk or its physical identity is unknown"
        )
    encrypted = any(n["type"] == "crypt" for n in nodes)
    if encrypted != (expected["luks_uuid"] is not None) or (
        encrypted and expected["luks_uuid"] not in {n.get("uuid") for n in nodes}
    ):
        raise ValueError(
            "Recovery encryption differs from the signed early-unlock policy"
        )


def image_spec(image: Path) -> dict:
    # os-release is data, never source it as shell code.
    with tempfile.TemporaryDirectory(prefix="luxnix-image-inspect-") as directory:
        metadata = Path(directory) / "os-release"
        sb.run("objcopy", "--only-section=.osrel", "-O", "binary", image, metadata)
        values = metadata.read_text().rstrip("\0").splitlines()
    lines = [line for line in values if line.startswith("LUXNIX_MIGRATION_SPEC=")]
    if len(lines) != 1 or "ID=luxnix-migration" not in values:
        raise ValueError("Not a LuxNix migration UKI")
    spec = json.loads(json.loads(lines[0].split("=", 1)[1]))
    validate_spec(spec)
    if "payload" not in spec:
        raise ValueError("Loader lacks an authenticated external payload")
    return spec


BUILD_SETTINGS = (
    "interface",
    "address",
    "gateway",
    "controller_cidr",
    "recovery_uuid",
    "recovery_fstype",
    "recovery_luks_uuid",
)


def block_nodes(nodes):
    for node in nodes:
        yield node
        yield from block_nodes(node.get("children", []))


SETTINGS_FILE = "migration-settings.yml"


def plan_settings(host: str) -> Path:
    """Settings live beside the plan that devenv shell luxnix migrate saved."""
    from lx_administration.storage import recovery_media

    return recovery_media.STATE_ROOT / host / SETTINGS_FILE


def default_settings(args, host: dict) -> Path:
    """Use the plan's settings, discovering and saving them on first use."""
    path = plan_settings(args.host)
    if path.exists():
        print(f"Using settings saved with the plan: {path}", file=sys.stderr)
        return path
    import yaml

    values = observe_settings(args, args.host, host)
    session = os.environ.get("SSH_CONNECTION", "").split()
    if not values["controller_cidr"] and session:
        # The controller is the machine this SSH session comes from, but only on
        # the management network: the RAM environment has no VPN.
        client = ipaddress.IPv4Address(session[0])
        if client not in ipaddress.IPv4Interface(values["address"]).network:
            raise ValueError(
                f"This SSH session comes from {client}, outside the management "
                f"network {values['address']}; the RAM environment cannot reach it. "
                "Add --controller-cidr <controller wired ip>/32"
            )
        values["controller_cidr"] = f"{client}/32"
    if not values["controller_cidr"]:
        raise ValueError(
            "Set the controller address: add --controller-cidr <ip>/32, or run "
            "this over SSH from the controller on the management network"
        )
    text = yaml.safe_dump(values, sort_keys=False)
    if path.parent.is_dir():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
        print(f"Saved these settings with the plan: {path}", file=sys.stderr)
    else:
        path = Path(tempfile.mkdtemp(prefix="luxnix-settings-")) / SETTINGS_FILE
        path.write_text(text)
        print("No saved plan on /recovery; using these settings once.", file=sys.stderr)
    print(text, end="", file=sys.stderr)
    return path


def build_settings(args, host):
    """Read data only; settings cannot select code, signing or output paths."""
    from lx_administration.yaml import load_unique_yaml_file

    if not args.settings:
        args.settings = default_settings(args, host)
    if args.settings:
        values = load_unique_yaml_file(args.settings)
        if values is None:
            raise ValueError(
                f"{args.settings} is empty. Rerun without --settings: the settings "
                "are discovered and saved with the plan"
            )
        expected = {"host", "hardware_uuid", *BUILD_SETTINGS}
        if not isinstance(values, dict) or set(values) != expected:
            found = set(values) if isinstance(values, dict) else set()
            raise ValueError(
                f"{args.settings} does not match this version: unexpected "
                f"{sorted(found - expected) or 'none'}, missing "
                f"{sorted(expected - found) or 'none'}. Move it aside and rerun "
                "without --settings to rediscover"
            )
        if (values["host"], values["hardware_uuid"]) != (
            args.host,
            host["hardware_uuid"].lower(),
        ):
            raise ValueError("Build settings belong to another inventory host")
        if any(
            value is not None and not isinstance(value, str)
            for value in values.values()
        ):
            raise ValueError("Build settings values must be strings or null")
        for name in BUILD_SETTINGS:
            if getattr(args, name) is None:
                setattr(args, name, values[name])
    missing = [
        "--" + name.replace("_", "-")
        for name in BUILD_SETTINGS
        if name not in {"gateway", "recovery_luks_uuid"} and not getattr(args, name)
    ]
    if missing:
        raise ValueError("Supply build settings or flags: " + ", ".join(missing))


def discover(args):
    """Observe this host without building, mounting or changing boot state."""
    from lx_administration.yaml import load_unique_yaml_file
    import yaml

    host_name = socket.gethostname().split(".")[0]
    host = load_unique_yaml_file(args.flake / "autoconf/config.yml")["boot_storage"][
        "hosts"
    ][host_name]
    values = observe_settings(args, args.host or host_name, host)
    if args.format == "command":
        if not args.controller_cidr:
            raise ValueError("--format command requires --controller-cidr")
        command = [
            "devenv",
            "shell",
            "migration-boot",
            "build",
            host_name,
            "--flake",
            str(args.flake.resolve()),
        ]
        for name in BUILD_SETTINGS:
            if values[name] is not None:
                command.extend(["--" + name.replace("_", "-"), values[name]])
        command.extend(
            ["--output", str(args.output or Path.home() / f"migration-{host_name}")]
        )
        print(shlex.join(command))
    else:
        print(yaml.safe_dump(values, sort_keys=False), end="")


def observe_settings(args, selected: str, host: dict) -> dict:
    """Read the network and recovery drive of this host; changes nothing."""
    host_name = socket.gethostname().split(".")[0]
    if selected != host_name:
        raise ValueError("Run discovery on the selected host, not its controller")
    recovery = getattr(args, "recovery", None) or Path("/recovery")
    routes = json.loads(sb.run("ip", "-json", "-4", "route", "show", "default"))
    if args.interface:
        routes = [r for r in routes if r.get("dev") == args.interface]
    if not args.interface and len(routes) != 1:
        raise ValueError("Default route is missing or ambiguous; select --interface")
    interface = args.interface or routes[0]["dev"]
    if len(routes) > 1:
        raise ValueError("Multiple default routes on the selected interface")
    addresses = json.loads(
        sb.run("ip", "-json", "-4", "address", "show", "dev", interface)
    )
    addresses = [
        f"{a['local']}/{a['prefixlen']}"
        for link in addresses
        for a in link.get("addr_info", [])
        if a.get("scope") == "global"
    ]
    if not args.address and len(addresses) != 1:
        raise ValueError("IPv4 address is missing or ambiguous; supply --address")
    mounts = mounted_filesystems(
        recovery, "SOURCE,UUID,FSTYPE,FSROOT", RECOVERY_MOUNT_FIX
    )
    if len(mounts) != 1 or mounts[0].get("fsroot") != "/":
        raise ValueError("Select a mounted recovery filesystem root")
    mount = mounts[0]
    if mount.get("fstype") not in RECOVERY_FILESYSTEMS or not mount.get("uuid"):
        raise ValueError("Recovery needs ext4 or Btrfs and a filesystem UUID")
    nodes = list(
        block_nodes(
            json.loads(
                sb.run(
                    "lsblk",
                    "--json",
                    "--inverse",
                    "--paths",
                    "--output",
                    "NAME,TYPE,FSTYPE,UUID",
                    mount["source"],
                )
            )["blockdevices"]
        )
    )
    luks = [
        n["uuid"] for n in nodes if n.get("fstype") == "crypto_LUKS" and n.get("uuid")
    ]
    if len(luks) > 1 or (any(n["type"] == "crypt" for n in nodes) and not luks):
        raise ValueError("Recovery encryption identity is ambiguous")
    values = {
        "host": host_name,
        "hardware_uuid": host["hardware_uuid"].lower(),
        "interface": interface,
        "address": args.address or addresses[0],
        "gateway": args.gateway or (routes[0].get("gateway") if routes else None),
        "controller_cidr": args.controller_cidr,
        "recovery_uuid": mount["uuid"],
        "recovery_fstype": mount["fstype"],
        "recovery_luks_uuid": luks[0] if luks else None,
    }
    if Path(f"/sys/class/net/{interface}/wireless").exists():
        print(
            "Wi-Fi detected: the RAM image does not configure wireless association. "
            "Use the local console or select wired networking.",
            file=sys.stderr,
        )
    if not args.controller_cidr:
        print(
            "Set controller_cidr to the allowed SSH controller IPv4/CIDR "
            "before building.",
            file=sys.stderr,
        )
    return values


def reviewed_spec(args, root: Path, boot_trust: str, console: str) -> dict:
    """The image specification from the reviewed checkout and the build settings."""
    from lx_administration.yaml import load_unique_yaml_file

    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", args.host):
        raise ValueError("Invalid inventory hostname")
    revision = sb.reviewed_source(root, root / "ansible/inventory/hosts.ini")
    config = load_unique_yaml_file(root / "autoconf/config.yml")
    host = config["boot_storage"]["hosts"][args.host]
    build_settings(args, host)
    admin = sb._nix(root, args.host, "user.admin.name")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", admin):
        raise ValueError("Unsupported administrator account name")
    spec = {
        "host": args.host,
        "boot_trust": boot_trust,
        "console": console,
        "hardware_uuid": host["hardware_uuid"].lower(),
        "revision": revision,
        "interface": args.interface,
        "address": args.address,
        "gateway": args.gateway,
        "controller_cidr": args.controller_cidr,
        "authorized_keys": json.loads(
            sb._nix(
                root,
                args.host,
                f"users.users.{admin}.openssh.authorizedKeys.keys",
                raw=False,
            )
        ),
        "recovery": {
            "uuid": args.recovery_uuid,
            "fstype": args.recovery_fstype,
            "luks_uuid": args.recovery_luks_uuid,
        },
        "target_serials": [disk["serial"] for disk in host["disks"]],
        "policy": load_unique_yaml_file(root / "conf/migration-environment.yml"),
    }
    validate_spec(spec)
    return spec


def build_attribute(root: Path, spec: dict, attribute: str) -> Path:
    expression = (
        f"let f = builtins.getFlake {json.dumps('git+file://' + str(root))}; "
        f"in (f.lib.migrationEnvironment (builtins.fromJSON "
        f"{json.dumps(json.dumps(spec))})).config.system.build.{attribute}"
    )
    return Path(
        sb.run(
            "nix",
            "build",
            "--impure",
            "--no-update-lock-file",
            "--no-link",
            "--print-out-paths",
            "--expr",
            expression,
        ).strip()
    )


def build(args) -> None:
    root = args.flake.resolve()
    spec = reviewed_spec(args, root, args.boot_trust, args.console)
    revision = spec["revision"]
    if not spec["authorized_keys"]:
        print("No SSH keys: local-console image will have SSH disabled.")
    output = build_attribute(root, spec, "migrationBundle")
    images = list(output.glob("*.efi"))
    manifest = json.loads((output / "manifest.json").read_text())
    if (
        len(images) != 1
        or image_spec(images[0]) != manifest
        or {key: value for key, value in manifest.items() if key != "payload"} != spec
    ):
        raise ValueError("Built image metadata differs from reviewed inputs")
    verify_payload(output / "migration.squashfs", manifest)
    if images[0].stat().st_size > spec["policy"]["maximum_image_mib"] * MIB:
        raise ValueError("RAM image exceeds the reviewed ESP size budget")
    if sb.reviewed_source(root, root / "ansible/inventory/hosts.ini") != revision:
        raise ValueError("Source changed during the build")
    # Signing is only reachable for an image built above from the reviewed source.
    args.output.mkdir(parents=True, exist_ok=False)
    destination = args.output / images[0].name
    shutil.copyfile(output / "migration.squashfs", args.output / "migration.squashfs")
    shutil.copyfile(output / "manifest.json", args.output / "manifest.json")
    if args.sign:
        sb._require_tty()
        with sb.private_workspace() as workspace:
            custody = workspace / "custody"
            certificate = sb.decrypt_pki(args.custody, custody)
            if certificate != (root / "conf/secure-boot/db.pem").read_bytes():
                raise ValueError("Custody does not match the reviewed fleet signer")
            keys = custody / "pki/keys/db"
            sb.run(
                "sbsign",
                "--key",
                keys / "db.key",
                "--cert",
                keys / "db.pem",
                "--output",
                destination,
                images[0],
            )
            sb.run("sbverify", "--cert", keys / "db.pem", destination)
    else:
        shutil.copyfile(images[0], destination)
    print(
        json.dumps(
            {
                "image": str(destination),
                "sha256": digest(destination),
                "signed": args.sign,
                "boot_trust": args.boot_trust,
                "payload": str(args.output / "migration.squashfs"),
                "payload_sha256": manifest["payload"]["sha256"],
                "host": args.host,
            },
            indent=2,
        )
    )


def prepare(args) -> None:
    """Build fresh reviewed artifacts, then preview or arm their firmware entry."""
    host = socket.gethostname().split(".")[0]
    if args.host not in (None, host):
        raise ValueError("Run this on the target host itself")
    args.host = host
    if not args.allow_unverified_boot:
        raise ValueError(
            "Console-approved boot requires --allow-unverified-boot; "
            "for firmware-authenticated boot use build --boot-trust secure-boot --sign"
        )
    directory = Path.home() / ".local/state/luxnix/migration-boot" / host
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Never select an older ~/migration-<host> bundle, even on a repeated run.
    args.output = Path(tempfile.mkdtemp(prefix="build-", dir=directory)) / "bundle"
    args.boot_trust, args.console, args.sign = "local-console", "tty1", False
    build(args)
    args.bundle = args.output
    args.image = args.payload = args.sha256 = None
    local_stage(args)
    if args.apply:
        print(
            "One-shot migration boot armed. Reboot when ready, approve BOOT UNVERIFIED "
            "at the target's screen, then run luxnix-migration run --apply."
        )
    else:
        print("Verified; no boot state changed. Repeat prepare with --apply to arm.")


def loader_variable(name: str) -> str | None:
    path = sb.EFIVARS / f"{name}-{LOADER_GUID}"
    if not path.exists():
        return None
    return path.read_bytes()[4:].decode("utf-16-le").rstrip("\0")


def require_default(esp: Path, entry: str) -> None:
    """A staged entry must never become the normal fallback by sort order."""
    default = loader_variable("LoaderEntryDefault")
    if not default:
        lines = (esp / "loader/loader.conf").read_text().splitlines()
        defaults = [
            line.split(None, 1)[1]
            for line in lines
            if line.strip().startswith("default ")
        ]
        if len(defaults) != 1:
            raise ValueError("Set an explicit normal boot default before staging")
        default = defaults[0]
    entries = json.loads(sb.run("bootctl", "--esp-path", esp, "list", "--json=short"))
    if (
        default.startswith("@")
        or fnmatch.fnmatchcase(entry, default)
        or not any(
            fnmatch.fnmatchcase(item["id"], default)
            and not item["id"].startswith("luxnix-migration-")
            for item in entries
        )
    ):
        raise ValueError("Normal boot default must exclude migration entries")


MIGRATION_PREFIX = "luxnix-migration-"


def set_loader_variable(name: str, entry: str) -> None:
    """Write one systemd-boot selection variable and read it back.

    An empty entry removes the variable, so loader.conf decides again.
    """
    verb = {"LoaderEntryDefault": "set-default", "LoaderEntryOneShot": "set-oneshot"}
    try:
        sb.run("bootctl", verb[name], entry)
    except sb.SecureBootError as error:
        raise ValueError(f"Could not set {name}: {error}") from error
    if (loader_variable(name) or "") != entry:
        raise ValueError(f"{name} did not read back as {entry or 'unset'}")


def hold_for_migration(host: str) -> dict:
    """Before the root changes, make every reboot return to this environment.

    Returns what to restore if nothing on the disk changes after all.
    """
    selected = loader_variable("LoaderEntrySelected")
    previous = loader_variable("LoaderEntryDefault")
    if not selected or not selected.startswith(f"{MIGRATION_PREFIX}{host}-"):
        return {"held": False, "previous": previous, "selected": selected}
    set_loader_variable("LoaderEntryDefault", selected)
    return {"held": True, "previous": previous, "entry": selected}


def release_hold(hold: dict) -> None:
    """Restore the default saved by hold_for_migration; the disk is unchanged."""
    if hold.get("held"):
        set_loader_variable("LoaderEntryDefault", hold.get("previous") or "")


def hand_over_boot(root: Path, esp: Path, closure: str) -> str:
    """Make the installed encrypted generation the firmware's real default.

    Clears every override so loader.conf, which NixOS keeps current on each
    rebuild, decides; then proves that default boots the planned closure.
    """
    from lx_administration.storage import root_guard

    link = os.readlink(root / "nix/var/nix/profiles/system")
    match = re.fullmatch(r"system-(\d+)-link", link)
    if match is None:
        raise ValueError(f"Unexpected installed system profile link: {link}")
    entry = f"nixos-generation-{match[1]}.conf"
    if root_guard.esp_generations(esp).get(int(match[1])) != closure:
        raise ValueError(f"Boot entry {entry} does not boot the planned closure")
    for name in ("LoaderEntryOneShot", "LoaderEntryDefault"):
        if loader_variable(name):
            set_loader_variable(name, "")
    defaults = [
        line.split(None, 1)[1].strip()
        for line in (esp / "loader/loader.conf").read_text().splitlines()
        if line.strip().startswith("default ")
    ]
    if defaults != [entry]:
        raise ValueError(
            f"loader.conf selects {defaults or 'no entry'}, not the installed {entry}"
        )
    return entry


def hardware_uuid() -> str:
    """The firmware UUID; the file is root-only, so an operator reads it via sudo."""
    path = Path("/sys/class/dmi/id/product_uuid")
    try:
        return path.read_text().strip().lower()
    except PermissionError:
        result = subprocess.run(
            ["sudo", "--", store_tool("cat"), str(path)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        return result.stdout.strip().lower()


def require_machine(spec: dict, host: str, certificate: Path) -> None:
    validate_spec(spec)
    if spec["host"] != host:
        raise ValueError("Signed image is for another inventory host")
    actual = hardware_uuid()
    if actual != spec["hardware_uuid"]:
        raise ValueError("Signed image is for another physical machine")
    if spec.get("boot_trust", "secure-boot") == "secure-boot":
        sb.firmware_check(certificate)
    memory = (
        int(
            next(
                line.split()[1]
                for line in Path("/proc/meminfo").read_text().splitlines()
                if line.startswith("MemTotal:")
            )
        )
        * 1024
    )
    if memory < spec["policy"]["minimum_memory_mib"] * MIB:
        raise ValueError("Insufficient RAM for the reviewed recovery environment")


def publish(path: Path, content: bytes | Path, expected: str | None = None) -> None:
    """Publish immutable boot artifacts; never replace an existing entry."""
    if path.is_symlink() or path.parent.resolve() != path.parent:
        raise ValueError("Refuse symlinked boot paths")
    expected = expected or (
        digest(content)
        if isinstance(content, Path)
        else hashlib.sha256(content).hexdigest()
    )
    if path.exists():
        if digest(path) != expected:
            raise ValueError("Existing boot artifact differs; refusing replacement")
        return
    fd, name = tempfile.mkstemp(prefix=".luxnix-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            if isinstance(content, Path):
                with content.open("rb") as source:
                    shutil.copyfileobj(source, stream)
            else:
                stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if digest(temporary) != expected:
            raise ValueError("Artifact changed during publication")
        # Holding the installer lock excludes other cooperating publishers.
        os.rename(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def local_stage(args) -> None:
    """Resolve local artifacts once, then use the same privileged stage checks."""
    args.host = args.host or socket.gethostname().split(".")[0]
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", args.host):
        raise ValueError("Invalid inventory hostname")
    explicit = (args.image, args.payload, args.sha256)
    if (args.bundle and any(explicit)) or (any(explicit) and not all(explicit)):
        raise ValueError("Use --bundle or all of --image, --payload and --sha256")
    if not any(explicit):
        bundle = (args.bundle or Path.home() / f"migration-{args.host}").expanduser()
        args.image = bundle / "migration.efi"
        args.payload = bundle / "migration.squashfs"
    for name in ("image", "payload", "certificate", "recovery", "esp"):
        path = getattr(args, name).expanduser().absolute()
        if not path.exists():
            raise ValueError(f"Missing --{name}: {path}")
        if name in {"image", "payload", "certificate"} and not path.is_file():
            raise ValueError(f"--{name} must be a regular file: {path}")
        setattr(args, name, path)
    args.sha256 = args.sha256 or digest(args.image)
    print(
        f"Stage {args.host}: {args.image}; recovery {args.recovery}; ESP {args.esp}",
        flush=True,
    )
    if os.geteuid() == 0:
        stage(args)
        return
    command = [
        "sudo",
        "--",
        "env",
        f"PATH={os.environ['PATH']}",
        sys.executable,
        "-B",
        "-m",
        "lx_administration.storage.migration_boot",
        "stage",
        args.host,
    ]
    for name in ("image", "payload", "sha256", "certificate", "recovery", "esp"):
        command.extend(["--" + name, str(getattr(args, name))])
    for name in ("apply", "allow_unverified_boot"):
        if getattr(args, name):
            command.append("--" + name.replace("_", "-"))
    subprocess.run(command, check=True)


def stage(args) -> None:
    import fcntl

    if os.geteuid() != 0:
        raise ValueError("Stage from a root terminal on the explicitly selected host")
    if not re.fullmatch(r"[0-9a-f]{64}", args.sha256):
        raise ValueError("Supply the reviewed signed-image SHA256")
    if args.image.is_symlink() or not stat.S_ISREG(args.image.stat().st_mode):
        raise ValueError("Image must be a regular file")
    if digest(args.image) != args.sha256:
        raise ValueError("Image SHA256 differs from the controller artifact")
    spec = image_spec(args.image)
    if spec.get("boot_trust") == "host-kexec":
        raise ValueError(
            "host-kexec images start with migration-boot kexec, not a boot entry"
        )
    local_console = spec.get("boot_trust", "secure-boot") == "local-console"
    if local_console != args.allow_unverified_boot:
        raise ValueError(
            "Local-console images require --allow-unverified-boot; "
            "secure images cannot be downgraded"
        )
    if local_console:
        print(
            "UNVERIFIED BOOT: no firmware authentication; "
            "physical console approval required at every boot."
        )
    else:
        sb.run("sbverify", "--cert", args.certificate, args.image)
    require_machine(spec, args.host, args.certificate)
    verify_payload(args.payload, spec)
    require_recovery(args.recovery, spec)
    payload_dir = args.recovery / "luxnix-migration"
    if payload_dir.resolve() != payload_dir:
        raise ValueError("Refuse symlinked payload directories")
    payload_path = payload_dir / (spec["payload"]["sha256"] + ".squashfs")
    if payload_path.exists():
        verify_payload(payload_path, spec)
    elif shutil.disk_usage(args.recovery).free < spec["payload"]["size"]:
        raise ValueError("Recovery filesystem lacks payload space")
    size = args.image.stat().st_size
    if size > spec["policy"]["maximum_image_mib"] * MIB:
        raise ValueError("Image exceeds the signed size budget")
    if not (loader_variable("LoaderInfo") or "").startswith("systemd-boot "):
        raise ValueError("One-shot migration currently requires systemd-boot")
    esp = args.esp
    if not esp.is_absolute() or esp.resolve() != esp:
        raise ValueError("ESP must be an absolute nonsymlinked mountpoint")
    mount = mounted_filesystems(
        esp, "FSTYPE", "mount the EFI system partition there or pass --esp"
    )
    if len(mount) != 1 or mount[0]["fstype"] != "vfat":
        raise ValueError("Selected ESP is not a mounted FAT filesystem")
    name = f"luxnix-migration-{args.host}-{args.sha256[:16]}"
    entry = name + ".conf"
    image = esp / "EFI/LuxNixMigration" / (name + ".efi")

    def require_capacity():
        # Repeating a verified publication needs no second copy of the image.
        if image.exists() and digest(image) != args.sha256:
            raise ValueError("Existing boot artifact differs; refusing replacement")
        needed = 0 if image.exists() else size
        reserve = spec["policy"]["esp_reserve_mib"] * MIB
        if shutil.disk_usage(esp).free < needed + reserve:
            raise ValueError(
                "ESP lacks space; do not repartition or delete recovery entries"
            )

    require_default(esp, entry)
    oneshot = loader_variable("LoaderEntryOneShot")
    if oneshot and oneshot != entry:
        raise ValueError("Another one-shot boot is already armed")
    require_capacity()
    if not args.apply:
        print(f"Verified {args.host}: stage {entry}; no boot state changed")
        return
    lock_fd = os.open(
        "/run/luxnix-migration-boot.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(lock_fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require_default(esp, entry)
        if loader_variable("LoaderEntryOneShot") not in (None, "", entry):
            raise ValueError("Another one-shot boot was armed during staging")
        require_capacity()
        for directory in (esp / "EFI/LuxNixMigration", esp / "loader/entries"):
            if directory.resolve() != directory:
                raise ValueError("Refuse symlinked boot directories")
            directory.mkdir(parents=True, exist_ok=True)
        require_recovery(args.recovery, spec)
        if payload_dir.resolve() != payload_dir:
            raise ValueError("Refuse symlinked payload directories")
        payload_dir.mkdir(mode=0o700, exist_ok=True)
        if (
            not payload_path.exists()
            and shutil.disk_usage(args.recovery).free < spec["payload"]["size"]
        ):
            raise ValueError("Recovery filesystem lacks payload space")
        publish(payload_path, args.payload, spec["payload"]["sha256"])
        verify_payload(payload_path, spec)
        content = args.image.read_bytes()
        if hashlib.sha256(content).hexdigest() != args.sha256:
            raise ValueError("Image changed during staging")
        publish(image, content)
        if not local_console:
            sb.run("sbverify", "--cert", args.certificate, image)
        publish(
            esp / "loader/entries" / entry,
            (
                f"title LuxNix migration ({args.host})\n"
                f"efi /EFI/LuxNixMigration/{name}.efi\n"
            ).encode(),
        )
        sb.run("bootctl", "--esp-path", esp, "set-oneshot", entry)
        if loader_variable("LoaderEntryOneShot") != entry:
            raise ValueError("Firmware did not retain the requested one-shot entry")
    print(
        f"Armed {entry}; normal default unchanged. No reboot or encryption performed."
    )


def admit(args) -> None:
    spec = json.loads(args.spec.read_text())
    require_machine(spec, spec["host"], args.certificate)
    if sb.run("findmnt", "-n", "-o", "FSTYPE", "--mountpoint", "/").strip() != "tmpfs":
        raise ValueError("Migration environment must run from RAM")
    if sb.run("swapon", "--show", "--noheadings", "--output", "NAME").strip():
        raise ValueError("Migration environment must not use swap")
    if spec.get("boot_trust") == "host-kexec":
        require_kexec_identity(spec)
    if spec.get("boot_trust", "secure-boot") == "local-console":
        console = "/dev/" + spec.get("console", "tty1")
        if not sys.stdin.isatty() or os.ttyname(sys.stdin.fileno()) != console:
            raise ValueError(
                "Unverified boot requires approval on the configured physical console"
            )
        phrase = f"BOOT UNVERIFIED {spec['host']} {spec['revision'][:12]}"
        print(
            "WARNING: firmware has NOT authenticated this migration environment.",
            flush=True,
        )
        print(
            "Payload integrity was checked, but a replaced loader "
            "could replace that check.",
            flush=True,
        )
        print(
            "Proceed only if you trust the staged image and physical machine. "
            "No encryption starts automatically.",
            flush=True,
        )
        if input(f"Type {phrase} to open migration access: ").strip() != phrase:
            raise ValueError("Local console approval declined")
    print("RAM environment admitted; migration still requires the existing plan gates")


KEXEC_RUN = Path("/run/luxnix-kexec")
KEXEC_ARCHIVE = "luxnix-kexec"
LOCKDOWN = Path("/sys/kernel/security/lockdown")
NETWORK = Path("/sys/class/net")


def require_kexec_identity(spec: dict) -> None:
    """SSH opens only with the host key that migration-boot kexec pinned."""
    try:
        identity = json.loads((KEXEC_RUN / "identity.json").read_text())
        public = (KEXEC_RUN / "ssh_host_ed25519_key.pub").read_text().split()[:2]
        key = (KEXEC_RUN / "ssh_host_ed25519_key").lstat()
    except (OSError, ValueError) as error:
        raise ValueError(
            "This RAM environment has no SSH host key from migration-boot kexec; "
            "SSH stays closed"
        ) from error
    if (
        identity.get("host") != spec["host"]
        or identity.get("revision") != spec["revision"]
        or str(identity.get("public_key", "")).split()[:2] != public
        or key.st_uid != 0
        or stat.S_IMODE(key.st_mode) != 0o600
    ):
        raise ValueError(
            "The SSH host key differs from the pinned one; SSH stays closed"
        )


def newc(entries: list[tuple[str, int, bytes | None]]) -> bytes:
    """A newc cpio archive; the kernel unpacks it on top of the initrd."""
    archive = bytearray()

    def pad() -> None:
        archive.extend(b"\0" * (-len(archive) % 4))

    trailer = ("TRAILER!!!", 0, b"")
    for number, (name, mode, data) in enumerate([*entries, trailer], 1):
        body = b"" if data is None else data
        encoded = name.encode() + b"\0"
        last = name == "TRAILER!!!"
        links = 1 if last or data is not None else 2
        fields = (0 if last else number, mode, 0, 0, links, 0, len(body))
        fields += (0, 0, 0, 0, len(encoded), 0)
        archive += b"070701" + b"".join(f"{value:08x}".encode() for value in fields)
        archive += encoded
        pad()
        archive += body
        pad()
    return bytes(archive)


def store_tool(name: str) -> str:
    found = shutil.which(name)
    real = os.path.realpath(found) if found else ""
    # Keep argv[0] for multicall tools (cat -> coreutils), but resolve their
    # containing directory so sudo never executes a mutable PATH entry.
    executable = (
        os.path.join(os.path.realpath(os.path.dirname(found)), os.path.basename(found))
        if found
        else ""
    )
    if not real.startswith("/nix/store/") or not executable.startswith("/nix/store/"):
        raise ValueError(f"{name} from the Nix store is required; use the devenv shell")
    return executable


def as_root(*command: str) -> None:
    prefix = [] if os.geteuid() == 0 else ["sudo", "--"]
    subprocess.run([*prefix, store_tool(command[0]), *command[1:]], check=True)


def kexec_bundle(args, host: str) -> tuple[Path, dict]:
    if args.bundle is not None:
        bundle = args.bundle.resolve()
        spec = json.loads((bundle / "manifest.json").read_text())
    else:
        root = args.flake.resolve()
        args.host = host
        spec = reviewed_spec(args, root, "host-kexec", "tty1")
        print("Building the RAM environment; this can take a while.", flush=True)
        bundle = build_attribute(root, spec, "kexecBundle")
        if json.loads((bundle / "manifest.json").read_text()) != spec:
            raise ValueError("Built RAM environment differs from the reviewed inputs")
        if (
            sb.reviewed_source(root, root / "ansible/inventory/hosts.ini")
            != spec["revision"]
        ):
            raise ValueError("Source changed during the build")
    validate_spec(spec)
    if spec.get("boot_trust") != "host-kexec" or spec["host"] != host:
        raise ValueError(f"The bundle is not a host-kexec image for {host}")
    for name in ("kernel", "initrd", "cmdline"):
        if not (bundle / name).is_file():
            raise ValueError(f"The bundle lacks its {name}")
    return bundle, spec


def management_link(spec: dict) -> bytes:
    """Keep the management interface's name, matched by its hardware address."""
    device = NETWORK / spec["interface"]
    if not device.exists():
        raise ValueError(f"Management interface {spec['interface']} does not exist")
    if (device / "addr_assign_type").read_text().strip() != "0":
        raise ValueError(
            f"{spec['interface']} uses a changed hardware address; select a wired "
            "interface with its permanent address"
        )
    address = (device / "address").read_text().strip()
    return (
        f"[Match]\nPermanentMACAddress={address}\n\n[Link]\nName={spec['interface']}\n"
    ).encode()


ARP = Path("/proc/net/arp")
ARP_COMPLETE = 0x2


def neighbor_present(address: str, interface: str) -> bool:
    for line in ARP.read_text().splitlines()[1:]:
        fields = line.split()
        if (
            len(fields) >= 6
            and fields[0] == address
            and fields[5] == interface
            and int(fields[2], 16) & ARP_COMPLETE
        ):
            return True
    return False


def require_controller_link(spec: dict, attempts: int = 6) -> None:
    """Refuse a switch that would leave the RAM environment unreachable.

    Only the management interface exists after kexec and SSH is accepted only from
    controller_cidr, so its next hop (the controller itself, or the gateway) must
    answer ARP on that interface now. A UDP datagram to the discard port triggers
    resolution without any controller service or ICMP policy.
    """
    network = ipaddress.IPv4Network(spec["controller_cidr"])
    interface = spec["interface"]
    subnet = ipaddress.IPv4Interface(spec["address"]).network
    controller = network.network_address
    if network.num_addresses == 1 and controller in subnet:
        hop, role = str(controller), "controller"
    elif spec.get("gateway"):
        hop, role = spec["gateway"], "gateway"
    else:
        raise ValueError(
            f"Controller {network} is outside {subnet} and no gateway is set; the "
            "RAM environment could not reach it. Use --controller-cidr <wired "
            "controller address>/32 on this subnet or set --gateway"
        )
    for attempt in range(attempts):
        if neighbor_present(hop, interface):
            return
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            try:
                probe.sendto(b"", (hop, 9))
            except OSError:
                pass
        if attempt + 1 < attempts:
            time.sleep(0.5)
    raise ValueError(
        f"No {role} answers at {hop} on {interface}; after the switch SSH is "
        f"accepted only from {network} over {interface}, so nobody could connect. "
        "Connect the controller to this wired network, or rebuild with "
        "--controller-cidr <its wired address>/32. Nothing was loaded"
    )


def require_controller_session(spec: dict) -> str | None:
    """Refuse a switch that would lock out the operator's own SSH session.

    A session arriving on the management network shows the controller's real
    address there. Returns a note when the address cannot be verified this way.
    """
    allowed = ipaddress.IPv4Network(spec["controller_cidr"])
    subnet = ipaddress.IPv4Interface(spec["address"]).network
    session = os.environ.get("SSH_CONNECTION", "").split()
    try:
        client = ipaddress.ip_address(session[0]) if session else None
    except ValueError:
        client = None
    if isinstance(client, ipaddress.IPv4Address) and client in subnet:
        if client not in allowed:
            raise ValueError(
                f"This SSH session comes from {client}, but the RAM environment "
                f"would accept SSH only from {allowed}: you could not reconnect. "
                f"Rerun with --controller-cidr {client}/32. Nothing was loaded"
            )
        return None
    if not allowed.subnet_of(subnet):
        return (
            f"NOT VERIFIED: {allowed} is outside the management network {subnet}. "
            "SSH will work only if that address reaches this host through "
            f"{spec.get('gateway') or 'a router'} unchanged. If your controller is on "
            f"{subnet}, stop and use --controller-cidr <its address there>/32"
        )
    return None


def kexec(args) -> None:
    """Build, then start the RAM environment in place of the running system."""
    host = socket.gethostname().split(".")[0]
    if args.host not in (None, host):
        raise ValueError("Run this on the target host itself")
    bundle, spec = kexec_bundle(args, host)
    require_machine(spec, host, Path("/dev/null"))
    if LOCKDOWN.exists() and "[none]" not in LOCKDOWN.read_text():
        raise ValueError(
            "Kernel lockdown (usually Secure Boot) blocks starting an unsigned "
            "RAM image; use the staged boot entry instead"
        )
    if not spec["authorized_keys"]:
        raise ValueError("Remote access needs administrator SSH keys in the inventory")
    link = management_link(spec)
    require_controller_link(spec)
    unverified = require_controller_session(spec)
    available = int(
        next(
            line.split()[1]
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemAvailable:")
        )
    )
    needed = sum((bundle / name).stat().st_size for name in ("kernel", "initrd"))
    if available * 1024 < 2 * needed + 512 * MIB:
        raise ValueError("Not enough free memory to load the RAM environment")
    address = str(ipaddress.IPv4Interface(spec["address"]).ip)
    port = spec["policy"]["ssh_port"]
    output = args.output or Path.home() / f"migration-{host}-kexec"
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    known_hosts = output / "known_hosts"
    with sb.private_workspace() as workspace:
        key = workspace / "ssh_host_ed25519_key"
        sb.run(
            "ssh-keygen", "-q", "-t", "ed25519", "-N", "",
            "-C", f"{host}-migration", "-f", key,
        )  # fmt: skip
        public = key.with_suffix(".pub").read_text().strip()
        fingerprint = sb.run("ssh-keygen", "-lf", key.with_suffix(".pub")).strip()
        identity = {"host": host, "revision": spec["revision"], "public_key": public}
        directory, public_line = KEXEC_ARCHIVE, f"{public}\n".encode()
        archive = newc(
            [
                (directory, 0o040700, None),
                (f"{directory}/ssh_host_ed25519_key", 0o100600, key.read_bytes()),
                (f"{directory}/ssh_host_ed25519_key.pub", 0o100644, public_line),
                (f"{directory}/identity.json", 0o100644, json.dumps(identity).encode()),
                (f"{directory}/10-luxnix-management.link", 0o100644, link),
            ]
        )
        initrd = workspace / "initrd"
        with initrd.open("wb") as stream, (bundle / "initrd").open("rb") as base:
            shutil.copyfileobj(base, stream)
            stream.write(b"\0" * (-stream.tell() % 4))
            stream.write(archive)
        known_hosts.write_text(f"[{address}]:{port} {' '.join(public.split()[:2])}\n")
        connect = (
            f"ssh -o UserKnownHostsFile={known_hosts} -o StrictHostKeyChecking=yes "
            f"-p {port} root@{address}"
        )
        print(
            f"RAM environment for {host}, revision {spec['revision'][:12]}\n"
            f"SSH: {address}:{port}, from {spec['controller_cidr']} only, "
            "administrator keys only\n"
            f"Host key: {fingerprint}\n"
            f"Pinned in: {known_hosts}\n"
            f"Connect with: {connect}" + (f"\n{unverified}" if unverified else ""),
            flush=True,
        )
        if not args.apply:
            print("Preview only; nothing was loaded. Add --apply to start it.")
            return
        sb._require_tty()
        phrase = f"START RAM {host}"
        print(
            f"\n{host} shuts down cleanly and the RAM environment starts in its place. "
            "Services stop and this connection ends; disks stay as they are. Copy "
            f"{known_hosts} to your controller first.",
            flush=True,
        )
        if input(f"Type {phrase} to continue: ").strip() != phrase:
            raise ValueError("Cancelled; nothing was loaded")
        as_root(
            "kexec", "--load", str(bundle / "kernel"), "--initrd", str(initrd),
            "--command-line", (bundle / "cmdline").read_text().strip(),
        )  # fmt: skip
    # The loaded kernel holds its own copy; the host key is gone from this disk.
    print(
        f"Loaded. Starting the RAM environment; reconnect with: {connect}", flush=True
    )
    as_root("systemctl", "kexec")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    discovery = commands.add_parser(
        "discover", help="Print local build settings without changes"
    )
    discovery.add_argument("host", nargs="?")
    discovery.add_argument("--flake", type=Path, default=sb.ROOT)
    discovery.add_argument("--recovery", type=Path, default=Path("/recovery"))
    for option in ("interface", "address", "gateway", "controller-cidr"):
        discovery.add_argument("--" + option)
    discovery.add_argument("--format", choices=("yaml", "command"), default="yaml")
    discovery.add_argument(
        "--output", type=Path, help="Output directory in the printed command"
    )
    builder = commands.add_parser("build")
    builder.add_argument("host")
    builder.add_argument("--flake", type=Path, default=sb.ROOT)
    for option in ("interface", "address", "controller-cidr"):
        builder.add_argument("--" + option)
    builder.add_argument("--gateway")
    builder.add_argument(
        "--settings", type=Path, help="Read discovery YAML; explicit flags override it"
    )
    builder.add_argument("--recovery-uuid")
    builder.add_argument("--recovery-fstype", choices=RECOVERY_FILESYSTEMS)
    builder.add_argument("--recovery-luks-uuid")
    builder.add_argument("--output", type=Path, required=True)
    builder.add_argument("--sign", action="store_true")
    builder.add_argument(
        "--boot-trust",
        choices=("secure-boot", "local-console"),
        default="local-console",
    )
    builder.add_argument("--console", choices=("tty1", "ttyS0"), default="tty1")

    builder.add_argument("--custody", type=Path, default=sb.DEFAULT_CUSTODY)
    target = commands.add_parser("stage")
    target.add_argument("host", nargs="?", help="Defaults to the local hostname")
    target.add_argument("--bundle", type=Path, help="Defaults to ~/migration-<host>")
    target.add_argument("--image", type=Path)
    target.add_argument("--sha256")
    target.add_argument("--payload", type=Path)
    target.add_argument("--recovery", type=Path, default=Path("/recovery"))
    target.add_argument(
        "--certificate", type=Path, default=sb.ROOT / "conf/secure-boot/db.pem"
    )
    target.add_argument("--esp", type=Path, default=Path("/boot"))
    target.add_argument("--apply", action="store_true")
    target.add_argument("--allow-unverified-boot", action="store_true")
    preparation = commands.add_parser(
        "prepare",
        help="Build a fresh console-approved image and verify or arm its one-shot boot",
    )
    preparation.add_argument("host", nargs="?", help="Defaults to the local hostname")
    preparation.add_argument("--flake", type=Path, default=sb.ROOT)
    preparation.add_argument("--settings", type=Path)
    for option in BUILD_SETTINGS:
        preparation.add_argument("--" + option.replace("_", "-"), dest=option)
    preparation.add_argument("--recovery", type=Path, default=Path("/recovery"))
    preparation.add_argument("--esp", type=Path, default=Path("/boot"))
    preparation.add_argument(
        "--certificate", type=Path, default=sb.ROOT / "conf/secure-boot/db.pem"
    )
    preparation.add_argument("--allow-unverified-boot", action="store_true")
    preparation.add_argument("--apply", action="store_true")
    starter = commands.add_parser(
        "kexec", help="Build, then start the RAM environment without a reboot"
    )
    starter.add_argument("host", nargs="?", help="Defaults to the local hostname")
    starter.add_argument("--flake", type=Path, default=sb.ROOT)
    for option in BUILD_SETTINGS:
        starter.add_argument("--" + option.replace("_", "-"), dest=option)
    starter.add_argument("--settings", type=Path)
    starter.add_argument("--bundle", type=Path, help="A prebuilt kexec bundle")
    starter.add_argument("--output", type=Path)
    starter.add_argument("--apply", action="store_true")
    admission = commands.add_parser("admit")
    admission.add_argument("--spec", type=Path, required=True)
    admission.add_argument("--certificate", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        {
            "discover": discover,
            "build": build,
            "prepare": prepare,
            "stage": local_stage,
            "admit": admit,
            "kexec": kexec,
        }[args.command](args)
    except (
        ValueError,
        EOFError,
        OSError,
        KeyError,
        sb.SecureBootError,
        subprocess.CalledProcessError,
    ) as error:
        parser.exit(1, f"Migration boot refused: {error}\n")


if __name__ == "__main__":
    main()
