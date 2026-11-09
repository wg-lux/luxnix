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
import uuid

from lx_administration import secure_boot as sb

MIB = 1024 * 1024
LOADER_GUID = "4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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
    if spec.get("boot_trust", "secure-boot") not in {"secure-boot", "local-console"}:
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
    if recovery["fstype"] not in {"ext4", "vfat"}:
        raise ValueError("Recovery payload filesystem must be ext4 or FAT")
    if recovery["fstype"] == "ext4":
        uuid.UUID(recovery["uuid"])
    elif not re.fullmatch(r"[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}", recovery["uuid"]):
        raise ValueError("Select the recovery filesystem UUID")
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
    mounts = json.loads(
        sb.run(
            "findmnt",
            "--json",
            "--mountpoint",
            path,
            "--output",
            "SOURCE,UUID,FSTYPE,FSROOT",
        )
    )["filesystems"]
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


def build_settings(args, host):
    """Read data only; settings cannot select code, signing or output paths."""
    from lx_administration.yaml import load_unique_yaml_file

    if args.settings:
        values = load_unique_yaml_file(args.settings)
        if not isinstance(values, dict) or set(values) != {
            "host",
            "hardware_uuid",
            *BUILD_SETTINGS,
        }:
            raise ValueError("Unexpected build settings fields")
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
    if args.host is not None and args.host != host_name:
        raise ValueError("Run discovery on the selected host, not its controller")
    host = load_unique_yaml_file(args.flake / "autoconf/config.yml")["boot_storage"][
        "hosts"
    ][host_name]
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
    mounts = json.loads(
        sb.run(
            "findmnt",
            "--json",
            "--mountpoint",
            args.recovery,
            "--output",
            "SOURCE,UUID,FSTYPE,FSROOT",
        )
    )["filesystems"]
    if len(mounts) != 1 or mounts[0].get("fsroot") != "/":
        raise ValueError("Select a mounted recovery filesystem root")
    mount = mounts[0]
    if mount.get("fstype") not in {"ext4", "vfat"} or not mount.get("uuid"):
        raise ValueError("Recovery needs ext4 or FAT and a filesystem UUID")
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


def build(args) -> None:
    from lx_administration.yaml import load_unique_yaml_file

    root = args.flake.resolve()
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
        "boot_trust": args.boot_trust,
        "console": args.console,
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
    if not spec["authorized_keys"]:
        print("No SSH keys: local-console image will have SSH disabled.")
    expression = (
        f"let f = builtins.getFlake {json.dumps('git+file://' + str(root))}; "
        f"in (f.lib.migrationEnvironment (builtins.fromJSON "
        f"{json.dumps(json.dumps(spec))})).config.system.build.migrationBundle"
    )
    output = Path(
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


def require_machine(spec: dict, host: str, certificate: Path) -> None:
    validate_spec(spec)
    if spec["host"] != host:
        raise ValueError("Signed image is for another inventory host")
    actual = Path("/sys/class/dmi/id/product_uuid").read_text().strip().lower()
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
    mount = json.loads(
        sb.run("findmnt", "--json", "--mountpoint", esp, "--output", "FSTYPE")
    )["filesystems"]
    if len(mount) != 1 or mount[0]["fstype"] != "vfat":
        raise ValueError("Selected ESP is not a mounted FAT filesystem")
    name = f"luxnix-migration-{args.host}-{args.sha256[:16]}"
    entry = name + ".conf"
    require_default(esp, entry)
    oneshot = loader_variable("LoaderEntryOneShot")
    if oneshot and oneshot != entry:
        raise ValueError("Another one-shot boot is already armed")
    if shutil.disk_usage(esp).free < size + spec["policy"]["esp_reserve_mib"] * MIB:
        raise ValueError(
            "ESP lacks space; do not repartition or delete recovery entries"
        )
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
        image = esp / "EFI/LuxNixMigration" / (name + ".efi")
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
    builder.add_argument("--recovery-fstype", choices=("ext4", "vfat"))
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
    admission = commands.add_parser("admit")
    admission.add_argument("--spec", type=Path, required=True)
    admission.add_argument("--certificate", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        {"discover": discover, "build": build, "stage": local_stage, "admit": admit}[
            args.command
        ](args)
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
