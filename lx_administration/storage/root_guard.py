"""Refuse root-storage generations that the physical disk cannot boot.

Runs on the target host from system.preSwitchChecks, never during Nix evaluation.
Reads hardware only. Its single mutation withdraws a just-refused generation from
the system profile. Standard library only: it ships inside the host closure.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid

if __package__:
    from . import boot
else:
    import boot

PLAINTEXT, ENCRYPTED = "plaintext", "encrypted"
ENCRYPTING, UNKNOWN = "encrypting", "unknown"
ROOT_FILESYSTEMS = {"btrfs", "ext4", "xfs"}
MUTATING = {"boot", "switch"}
ESP_MARGIN = 16 * 1024 * 1024
OVERRIDE_SECONDS = 900
RECEIPT = Path("var/lib/luxnix-boot-passphrase/cryptroot.json")
PROFILE_DIR = Path("nix/var/nix/profiles")
OVERRIDE = Path("/run/luxnix/root-guard-override.json")
AUDIT = Path("/var/lib/luxnix/root-guard-audit.jsonl")
CLOSURE = re.compile(r"/nix/store/[a-z0-9]{32}-nixos-system-[^/]+")
TRANSIENT_DISK = re.compile(r"/dev/(sd[a-z]+|vd[a-z]+|nvme\d+n\d+|hd[a-z]+)$")
GENERATION = re.compile(r"system-(\d+)-link")


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    # A hard finding describes physical incompatibility: no override can fix it.
    hard: bool = True


def run(*args: str) -> str | None:
    """Return stdout, or None when the probe fails; callers fail closed on None."""
    try:
        result = subprocess.run(
            args, text=True, capture_output=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def resolve(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return str(Path(path).resolve(strict=True))
    except OSError:
        return None


def under(root: Path, path: str) -> Path:
    return root / path.lstrip("/")


def probe_luks(partition: str) -> dict | None:
    raw = run("cryptsetup", "luksDump", "--dump-json-metadata", partition)
    if raw is None:
        return None
    try:
        metadata = json.loads(raw)
        if not all(isinstance(metadata.get(key), dict)
                   for key in ("config", "segments", "keyslots")):
            return None
        if not metadata["segments"] or not metadata["keyslots"]:
            return None
        mandatory = metadata["config"].get("requirements", {}).get("mandatory", [])
        if not isinstance(mandatory, list) or any(
            not isinstance(item, str) for item in mandatory
        ):
            return None
    except (ValueError, AttributeError, TypeError):
        return None
    return {
        "version": 2
        if run("cryptsetup", "isLuks", "--type", "luks2", partition) == ""
        else 1,
        "uuid": run("cryptsetup", "luksUUID", partition),
        "reencrypting": any("reencrypt" in item for item in mandatory),
    }


def classify_root(signature: str | None, luks: dict | None) -> str:
    """Classify observed partition metadata; missing evidence is never plaintext."""
    if signature == "crypto_LUKS":
        if (
            not isinstance(luks, dict)
            or luks.get("version") != 2
            or not isinstance(luks.get("uuid"), str)
            or not isinstance(luks.get("reencrypting"), bool)
        ):
            return UNKNOWN
        try:
            uuid.UUID(luks["uuid"])
        except ValueError:
            return UNKNOWN
        return ENCRYPTING if luks["reencrypting"] else ENCRYPTED
    return PLAINTEXT if signature in ROOT_FILESYSTEMS else UNKNOWN


def mounted_root_state(root: Path) -> str:
    """Classify every filesystem member; uncertainty never selects a generation."""
    try:
        mount = probe_mount(root)
        if mount is None or mount["fstype"] not in ROOT_FILESYSTEMS:
            return UNKNOWN
        states = {member_state(device, mount["fstype"])
                  for device in boot.filesystem_devices(mount)}
        if len(states) == 1:
            return next(iter(states))
        if states and states <= {ENCRYPTED, ENCRYPTING}:
            return ENCRYPTING
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        pass
    return UNKNOWN


def member_state(device: str, fstype: str) -> str:
    tree = json.loads(run(
        "lsblk", "--json", "--paths", "--inverse", "--output", "NAME,TYPE", device
    ) or "null")
    if not isinstance(tree, dict) or len(tree.get("blockdevices", [])) != 1:
        return UNKNOWN

    def boundaries(node: dict) -> set[str]:
        if not isinstance(node, dict) or not str(node.get("name", "")).startswith(
            "/dev/"
        ):
            return {UNKNOWN}
        if node.get("type") not in {
            "disk", "part", "crypt", "raid0", "raid1", "raid4", "raid5",
            "raid6", "raid10", "md", "lvm", "mpath", "dm", "linear",
        }:
            return {UNKNOWN}
        children = node.get("children", [])
        if not isinstance(children, list):
            return {UNKNOWN}
        if node.get("type") == "crypt":
            if len(children) != 1 or not isinstance(children[0], dict):
                return {UNKNOWN}
            backing = children[0].get("name")
            if not isinstance(backing, str) or not backing.startswith("/dev/"):
                return {UNKNOWN}
            return {classify_root("crypto_LUKS", probe_luks(backing))}
        if children:
            return set().union(*(boundaries(child) for child in children))
        return {PLAINTEXT} if node.get("type") == "disk" else {UNKNOWN}

    states = boundaries(tree["blockdevices"][0])
    if states == {PLAINTEXT}:
        signature = run(
            "blkid", "--probe", "--output", "value", "--match-tag", "TYPE", device
        )
        return PLAINTEXT if signature == fstype else UNKNOWN
    if states and states <= {ENCRYPTED, ENCRYPTING}:
        boot.require_luks2(device)
        return ENCRYPTING if ENCRYPTING in states else ENCRYPTED
    return UNKNOWN



def probe_mapping(name: str) -> dict | None:
    device = Path("/dev/mapper") / name
    try:
        info = device.stat()
    except OSError:
        return None
    node = Path("/sys/dev/block") / f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}"
    try:
        dm_uuid = (node / "dm/uuid").read_text().strip()
        backing = [
            f"{os.major(os.stat('/dev/' + slave.name).st_rdev)}:"
            f"{os.minor(os.stat('/dev/' + slave.name).st_rdev)}"
            for slave in (node / "slaves").iterdir()
        ]
    except OSError:
        return None
    return {"dm_uuid": dm_uuid, "backing": backing}


def probe_mount(path: Path) -> dict | None:
    raw = run(
        "findmnt",
        "--json",
        "--mountpoint",
        str(path),
        "--output",
        "SOURCE,FSTYPE,UUID,FSROOT",
    )
    if raw is None:
        return None
    try:
        records = json.loads(raw).get("filesystems", [])
        if len(records) != 1:
            return None
        return {
            "source": records[0]["source"].split("[", 1)[0],
            "fstype": records[0]["fstype"],
            "uuid": records[0].get("uuid"),
            "fsroot": records[0].get("fsroot"),
        }
    except (ValueError, AttributeError, KeyError, TypeError):
        return None


def probe_receipt(root: Path, partition: str | None) -> dict | None:
    path = root / RECEIPT
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            return None
        receipt = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if partition is None:
        return None
    return {
        "uuid": receipt.get("uuid"),
        "matches_header": header_matches(receipt, partition),
    }


def header_matches(receipt: dict, partition: str) -> bool:
    if __package__:
        from . import boot_password
    else:
        import boot_password
    try:
        return boot_password.header_digest(partition) == receipt.get("header_sha256")
    except (OSError, ValueError, KeyError, TypeError):
        return False


def root_kind_of_generation(path: Path) -> str | None:
    """Read which root device a retained generation mounts, from its own fstab."""
    try:
        lines = (path / "etc/fstab").read_text().splitlines()
    except OSError:
        return None
    roots = [line.split() for line in lines if not line.lstrip().startswith("#")
             and len(line.split()) >= 3 and line.split()[1] == "/"]
    if len(roots) != 1 or roots[0][2] not in ROOT_FILESYSTEMS:
        return None
    device = roots[0][0]
    if device == "/dev/mapper/cryptroot":
        return ENCRYPTED
    # An unfamiliar mapper or filesystem UUID may refer to an encrypted device.
    # Its initrd contract cannot be inferred from this fstab entry alone.
    if not device.startswith("/dev/") or device.startswith(
        ("/dev/mapper/", "/dev/dm-", "/dev/disk/by-uuid/")
    ):
        return None
    return PLAINTEXT


def esp_generations(esp: Path) -> dict[int, str | None]:
    """Map generations with a usable EFI entry to the closure that entry boots.

    systemd-boot entries are verified: their kernel and initrd exist and init=
    names the closure. A signed unified image only proves its filename, so None.
    """
    found: dict[int, str | None] = {}
    for entry in esp.glob("loader/entries/nixos-generation-*.conf"):
        match = re.fullmatch(r"nixos-generation-(\d+)\.conf", entry.name)
        if not match:
            continue
        try:
            fields = dict(
                line.split(None, 1)
                for line in entry.read_text().splitlines()
                if " " in line
            )
        except OSError:
            continue
        init = re.search(
            r"\binit=(/nix/store/[^/\s]+)/init\b", fields.get("options", "")
        )
        files = [fields.get("linux", ""), fields.get("initrd", "")]
        if init and all(
            item and (esp / item.strip().lstrip("/")).is_file() for item in files
        ):
            found[int(match[1])] = init[1]
    for image in esp.glob("EFI/Linux/nixos-generation-*.efi"):
        match = re.match(r"nixos-generation-(\d+)", image.name)
        if match:
            found.setdefault(int(match[1]), None)
    return found


def probe_generations(root: Path, esp: str = "/boot") -> list[dict]:
    on_esp = esp_generations(under(root, esp))
    generations = []
    try:
        entries = list((root / PROFILE_DIR).iterdir())
    except OSError:
        return []
    for entry in entries:
        match = GENERATION.fullmatch(entry.name)
        if match:
            generations.append(
                {
                    "number": int(match[1]),
                    "system": os.path.realpath(entry),
                    "root": root_kind_of_generation(entry),
                    "on_esp": int(match[1]) in on_esp
                    and on_esp[int(match[1])] in {None, os.path.realpath(entry)},
                }
            )
    return sorted(generations, key=lambda item: item["number"])


def probe_esp(root: Path, esp: str, system: str | None) -> dict | None:
    path = under(root, esp)
    try:
        stats = os.statvfs(path)
        kernel, initrd = (Path(system or "") / "kernel", Path(system or "") / "initrd")
        needed = kernel.stat().st_size + initrd.stat().st_size
    except OSError:
        return None
    # systemd-boot deduplicates files already copied to the ESP by store hash.
    for link in (kernel, initrd):
        name = Path(os.path.realpath(link))
        copied = path / "EFI/nixos" / f"{name.parent.name}-{name.name}.efi"
        if copied.exists():
            needed -= link.stat().st_size
    return {"free": stats.f_bavail * stats.f_frsize, "needed": max(needed, 0)}


def observe(spec: dict, *, root: Path = Path("/"), system: str | None = None) -> dict:
    target = spec["root"]
    partition = resolve(target["partition"])
    disk = resolve(target["disk"])
    signature = (
        run("blkid", "--probe", "--output", "value", "--match-tag", "TYPE", partition)
        if partition
        else None
    )
    parent = (
        run(
            "lsblk",
            "--noheadings",
            "--paths",
            "--nodeps",
            "--output",
            "PKNAME",
            partition,
        )
        if partition
        else None
    )
    mapping = target.get("mapping")
    mapper_stat = probe_mapping(mapping) if mapping else None
    partition_number = None
    if partition:
        info = os.stat(partition)
        partition_number = f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}"
    mounts = {
        path: probe_mount(under(root, path) if path != "/" else root)
        for path in spec["mounts"]
    }
    return {
        "partition": partition,
        "partition_number": partition_number,
        "disk": disk,
        "parent": parent,
        "signature": signature,
        "luks": probe_luks(partition) if signature == "crypto_LUKS" else None,
        "mapping": mapper_stat,
        "mounts": mounts,
        "receipt": probe_receipt(root, partition),
        "esp": probe_esp(root, spec["bootloader"]["esp"], system),
        "generations": probe_generations(root, spec["bootloader"]["esp"]),
        "firmware_efi": Path("/sys/firmware/efi").is_dir(),
    }


def identity_findings(spec: dict, seen: dict) -> list[Finding]:
    target = spec["root"]
    disk = target["disk"]
    findings = []
    if seen["partition"] is None:
        return [
            Finding(
                "partition-missing",
                f"Configured root partition {target['partition']} does not exist",
            )
        ]
    if disk is None:
        findings.append(
            Finding(
                "disk-undeclared",
                "The root partition has no declared owning disk",
                False,
            )
        )
    elif TRANSIENT_DISK.match(disk):
        # A kernel name can change between boots, so it identifies nothing.
        if target["require_persistent_disk"]:
            findings.append(
                Finding(
                    "disk-not-persistent",
                    f"{disk} is not a persistent hardware identity; "
                    "use /dev/disk/by-id",
                )
            )
    elif seen["disk"] is None:
        findings.append(
            Finding("disk-missing", f"Declared root disk {disk} does not exist")
        )
    elif seen["parent"] != seen["disk"]:
        findings.append(
            Finding(
                "partition-identity",
                f"{target['partition']} is on {seen['parent']}, not on declared "
                f"disk {seen['disk']}",
            )
        )
    return findings


def mount_findings(spec: dict, seen: dict) -> list[Finding]:
    findings = []
    for path, expected in spec["mounts"].items():
        mounted = seen["mounts"].get(path)
        if mounted is None:
            findings.append(
                Finding("mount-missing", f"{path} is not mounted exactly once")
            )
            continue
        if mounted["fstype"] != expected["fsType"]:
            findings.append(
                Finding(
                    "mount-type",
                    f"{path} is {mounted['fstype']}, not {expected['fsType']}",
                )
            )
        if resolve(mounted["source"]) != resolve(expected["device"]):
            findings.append(
                Finding(
                    "mount-source",
                    f"{path} is mounted from {mounted['source']}, "
                    f"not {expected['device']}",
                )
            )
        subvolume = expected.get("subvolume")
        if subvolume and mounted.get("fsroot") != "/" + subvolume.lstrip("/"):
            findings.append(
                Finding("subvolume", f"{path} is not Btrfs subvolume {subvolume}")
            )
    return findings


def encrypted_findings(spec: dict, seen: dict) -> list[Finding]:
    target = spec["root"]
    actual = seen["signature"]
    initrd = spec["initrd"]
    if not initrd["systemd"] or not initrd["unlocks_root"]:
        return [
            Finding("initrd", "This generation's initrd cannot unlock encrypted root")
        ]
    if actual != "crypto_LUKS":
        return [
            Finding(
                "root-not-luks",
                "This generation requires encrypted root, but "
                f"{target['partition']} contains "
                f"{actual or 'an unidentified signature'}. "
                "A rebuild cannot encrypt a disk and this generation would not boot.",
            )
        ]
    luks = seen["luks"]
    if luks is None or luks["version"] != 2 or not luks["uuid"]:
        return [
            Finding("luks-header", "The root partition has no readable LUKS2 header")
        ]
    findings = []
    if initrd["plaintext_bridge"]:
        findings.append(
            Finding(
                "plaintext-bridge",
                "This initrd can boot plaintext root, but the disk is now encrypted; "
                "disable plaintextRootBridge",
            )
        )
    if luks["reencrypting"]:
        findings.append(
            Finding(
                "root-reencrypting",
                "Encryption is incomplete; finish it from the installer",
            )
        )
    expected = target.get("expected_luks_uuid")
    if expected and luks["uuid"] != expected:
        findings.append(
            Finding(
                "luks-uuid",
                f"Root LUKS UUID {luks['uuid']} is not the pinned {expected}",
            )
        )
    mapping = seen["mapping"]
    name = target["mapping"]
    wanted = f"CRYPT-LUKS2-{luks['uuid'].replace('-', '')}-{name}"
    if mapping is None:
        findings.append(Finding("mapping-missing", f"/dev/mapper/{name} is not open"))
    elif mapping["dm_uuid"] != wanted or mapping["backing"] != [
        seen["partition_number"]
    ]:
        findings.append(
            Finding(
                "mapping-identity",
                f"/dev/mapper/{name} is not the LUKS2 mapping of the "
                "configured partition",
            )
        )
    return findings


def plaintext_findings(spec: dict, seen: dict) -> list[Finding]:
    target = spec["root"]
    actual = seen["signature"]
    if spec["initrd"]["unlocks_root"]:
        return [Finding("initrd", "A plaintext-root layout must not unlock cryptroot")]
    if actual == "crypto_LUKS":
        return [
            Finding(
                "root-is-luks",
                "This generation mounts plaintext root, but "
                f"{target['partition']} is LUKS. It would not boot; select boot-luks.",
            )
        ]
    if actual != target["fsType"]:
        return [
            Finding(
                "root-filesystem",
                f"{target['partition']} contains "
                f"{actual or 'an unidentified signature'}, "
                f"not {target['fsType']}",
            )
        ]
    return []


def receipt_findings(
    spec: dict, seen: dict, *, optional: bool = False
) -> list[Finding]:
    receipt = seen["receipt"]
    uuid = (seen["luks"] or {}).get("uuid")
    if receipt is None and optional:
        return []
    if receipt is None or receipt["uuid"] != uuid or not receipt["matches_header"]:
        return [
            Finding(
                "recovery-credential",
                "No verified disk-passphrase receipt matches this LUKS2 header. Run "
                "`sudo luxnix-setup-boot-password` (safe to repeat), then retry.",
                False,
            )
        ]
    return []


def capacity_findings(
    spec: dict, seen: dict, system: str, first_install: bool
) -> list[Finding]:
    findings = []
    loader = spec["bootloader"]
    if (
        loader["kind"] != "none"
        and loader["efi_variables"]
        and not seen["firmware_efi"]
    ):
        findings.append(Finding("firmware", "This host did not boot through UEFI"))
    esp = seen["esp"]
    if esp is None:
        findings.append(
            Finding("esp", "Cannot measure the EFI partition for this generation")
        )
    elif esp["free"] < esp["needed"] + ESP_MARGIN:
        findings.append(
            Finding(
                "esp-capacity",
                f"The EFI partition has {esp['free']} bytes free but needs "
                f"{esp['needed'] + ESP_MARGIN}; remove old generations first",
                False,
            )
        )
    limit = spec["bootloader"]["limit"]
    if limit is not None and limit < 2:
        findings.append(
            Finding("retention", "Boot entry retention below 2 cannot keep a fallback")
        )
    kind = ENCRYPTED if spec["layout"] == "boot-luks" else PLAINTEXT
    retained = [item for item in seen["generations"] if item["system"] != system]
    if limit is not None:
        retained = retained[-(limit - 1) :] if limit > 1 else []
    usable = [item for item in retained if item["root"] == kind and item.get("on_esp")]
    if not first_install and not usable:
        findings.append(
            Finding(
                "no-fallback-generation",
                f"No other boot entry on the EFI partition mounts {kind} root, "
                "so a failure of "
                "this generation has no fallback. Keep recovery media ready.",
                False,
            )
        )
    return findings


def assess(
    spec: dict,
    seen: dict,
    *,
    action: str,
    system: str,
    first_install: bool = False,
    require_receipt: bool = False,
) -> list[Finding]:
    """Pure decision: compare one evaluated generation with one hardware snapshot."""
    findings = identity_findings(spec, seen)
    if any(item.code == "partition-missing" for item in findings):
        return findings
    # The explicitly enabled bridge boots this filesystem; encryption stays absent.
    if (
        spec["layout"] == "boot-luks"
        and spec["initrd"]["plaintext_bridge"]
        and seen["signature"] == spec["root"]["fsType"]
    ):
        return findings
    if spec["layout"] == "boot-luks":
        layout = encrypted_findings(spec, seen)
    else:
        layout = plaintext_findings(spec, seen)
    findings += layout
    if not layout:
        findings += mount_findings(spec, seen)
    if action in MUTATING:
        if spec["layout"] == "boot-luks" and not layout:
            # A fresh install has no receipt yet, but a stale one is never accepted.
            findings += receipt_findings(
                spec, seen, optional=first_install and not require_receipt
            )
        findings += capacity_findings(spec, seen, system, first_install)
    return findings


def audit(event: dict) -> None:
    AUDIT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(AUDIT, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as stream:
        stream.write(json.dumps(event | {"at": time.time()}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    subprocess.run(
        ["logger", "--tag", "luxnix-root-guard", json.dumps(event)],
        check=False,
        capture_output=True,
    )


def consume_override(system: str, findings: list[Finding], action: str) -> bool:
    """Use a one-shot override bound to this exact closure; hard findings ignore it."""
    if any(item.hard for item in findings):
        return False
    try:
        info = OVERRIDE.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            return False
        grant = json.loads(OVERRIDE.read_text())
    except (OSError, ValueError):
        return False
    OVERRIDE.unlink()
    if grant.get("system") != system or grant.get("expires", 0) < time.time():
        return False
    audit(
        {
            "event": "override-used",
            "system": system,
            "action": action,
            "operator": grant.get("operator"),
            "reason": grant.get("reason"),
            "findings": [item.code for item in findings],
        }
    )
    return True


def grant_override(spec: dict, system: str, operator: str, reason: str) -> None:
    if os.geteuid() != 0 or not sys.stdin.isatty():
        raise ValueError("An override needs root at an interactive terminal")
    if not CLOSURE.fullmatch(system) or not operator.strip() or not reason.strip():
        raise ValueError("An override needs an exact closure, operator and reason")
    phrase = f"OVERRIDE {spec['host']} {Path(system).name[:12]}"
    print("This allows one activation despite non-physical preflight findings.")
    if input(f"To proceed, type {phrase}: ").strip() != phrase:
        raise ValueError("Override cancelled")
    OVERRIDE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(OVERRIDE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(
            {
                "system": system,
                "operator": operator,
                "reason": reason,
                "expires": time.time() + OVERRIDE_SECONDS,
            },
            stream,
        )
    audit(
        {
            "event": "override-granted",
            "system": system,
            "operator": operator,
            "reason": reason,
        }
    )


def withdraw(system: str, root: Path = Path("/")) -> str:
    """Remove a refused generation so it cannot consume a boot-menu slot."""
    profile = root / PROFILE_DIR / "system"
    if root != Path("/") or os.path.realpath(profile) != system:
        return "The system profile does not point at this generation."
    link = GENERATION.fullmatch(os.readlink(profile))
    current = os.path.realpath(root / "run/current-system")
    if link is None or current == system:
        return "The active generation was left in the system profile."
    number = link[1]
    for args in (["--rollback"], ["--delete-generations", number]):
        if run("nix-env", "--profile", str(profile), *args) is None:
            return (
                f"WARNING: could not withdraw generation {number} from the system "
                "profile; delete it before the next rebuild."
            )
    return f"Refused generation {number} was withdrawn from the system profile."


def report(findings: list[Finding], stream=None) -> None:
    for item in findings:
        kind = "physical mismatch" if item.hard else "unmet requirement"
        print(f"  [{kind}] {item.code}: {item.message}", file=stream or sys.stderr)


def check(spec: dict, *, system: str, action: str, root: Path = Path("/")) -> int:
    seen = observe(spec, root=root, system=system)
    # A running host cannot claim first installation, even with this upstream variable.
    first_install = (
        os.environ.get("NIXOS_INSTALL_BOOTLOADER") == "1"
        and not Path("/run/booted-system").exists()
    )
    if os.environ.get("NIXOS_NO_CHECK") == "1":
        audit({"event": "no-check-environment", "system": system, "action": action})
    findings = assess(
        spec, seen, action=action, system=system, first_install=first_install
    )
    if not findings:
        return 0
    if action in MUTATING and consume_override(system, findings, action):
        print(
            "Root storage preflight overridden; the override was audited.",
            file=sys.stderr,
        )
        return 0
    print(f"LuxNix refused to {action} this system on {spec['host']}:", file=sys.stderr)
    report(findings)
    if action in MUTATING:
        print(withdraw(system, root), file=sys.stderr)
    print("Disks and boot entries were not changed.", file=sys.stderr)
    print(
        "Next: `luxnix-root-preflight status`; docs/boot-storage-recovery.md",
        file=sys.stderr,
    )
    return 1


def verify(spec: dict, *, system: str, action: str, root: Path = Path("/")) -> int:
    """The full check, for callers about to publish: never withdraws or consumes."""
    findings = assess(
        spec, observe(spec, root=root, system=system), action=action, system=system
    )
    if findings:
        print(f"This system cannot {action} on {spec['host']}:", file=sys.stderr)
        report(findings)
        return 1
    return 0


def status(spec: dict, root: Path = Path("/")) -> int:
    seen = observe(spec, root=root)
    current = os.path.realpath(root / PROFILE_DIR / "system")
    findings = assess(spec, seen, action="dry-activate", system=current)
    partition_kind = classify_root(seen["signature"], seen["luks"])
    mounted_kind = mounted_root_state(root)
    if ENCRYPTING in {partition_kind, mounted_kind}:
        kind = ENCRYPTING
    elif partition_kind == mounted_kind and not any(f.hard for f in findings):
        kind = partition_kind
    else:
        kind = UNKNOWN
    if kind == UNKNOWN:
        findings.append(Finding(
            "root-state-unknown",
            "Cannot verify complete mounted-root storage; inspect its mounts, "
            "filesystem members and LUKS headers before selecting a generation",
        ))
    elif kind == ENCRYPTING and not any(
        f.code == "root-reencrypting" for f in findings
    ):
        findings.append(Finding(
            "root-reencrypting",
            "Encryption is incomplete; resume it from recovery media",
        ))
    print(f"Host: {spec['host']}  layout: {spec['layout']}")
    print(
        f"Root partition: {spec['root']['partition']} -> "
        f"{seen['signature'] or 'unknown'}; state: {partition_kind}"
    )
    print(f"Mounted root state: {mounted_kind}")
    print("Retained generations (declared root layouts; boot success is unverified):")
    for item in seen["generations"]:
        if kind == UNKNOWN or item["root"] is None:
            label = "compatibility unknown"
        elif kind == ENCRYPTING:
            label = "incompatible: encryption incomplete"
        elif item["root"] != kind:
            label = "layout incompatible"
        else:
            label = "layout compatible; boot unverified"
            if not item.get("on_esp"):
                label += "; EFI entry unverified"
        print(f"  {item['number']}: {item['root'] or 'unknown'} root; {label}")
    if findings:
        print("This generation is not verified for this disk:")
        report(findings, sys.stdout)
        return 1
    print("This generation matches the disk.")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "verify", "status", "override"])
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--system")
    parser.add_argument("--action", default="dry-activate")
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--operator", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args(argv)
    try:
        spec = json.loads(args.spec.read_text())
        if args.command == "status":
            sys.exit(status(spec, args.root))
        if not args.system:
            raise ValueError("--system is required")
        if args.command == "override":
            grant_override(spec, args.system, args.operator, args.reason)
            return
        command = verify if args.command == "verify" else check
        sys.exit(command(spec, system=args.system, action=args.action, root=args.root))
    except (ValueError, KeyError, OSError, EOFError) as error:
        parser.exit(1, f"Root storage preflight failed closed: {error}\n")


if __name__ == "__main__":
    main()
