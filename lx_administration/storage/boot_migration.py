"""Guarded, local boot-storage migration evidence and install-only workflow.

Never partitions, formats, restores application data, creates volume keys,
activates, or reboots.
Human attestations are named as such; they are not automated restore proof.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

import yaml

from lx_administration.secret_storage import encrypted_storage, filesystem_devices
from lx_administration.storage.cutover import atomic_json

STAGES = {
    "recovery": (
        "console_boot_tested",
        "independent_credentials_tested",
        "headers_preserved",
        "trusted_installer_tested",
    ),
    "backup": (
        "archives_authenticated",
        "independent_copy_verified",
        "source_retained",
    ),
    "restore": (
        "isolated_restore_verified",
        "database_verified",
        "historical_media_decrypted",
        "identities_preserved",
    ),
    "prepared": (
        "target_layout_reviewed",
        "recovery_slots_tested",
        "identities_restored",
        "database_restored",
        "boot_artifacts_reviewed",
    ),
    "acceptance": (
        "offline_cold_boot_passed",
        "secondary_unlock_passed",
        "application_verified",
        "failure_tests_passed",
        "recovery_test_passed",
    ),
    "install-recovery": ("partial_install_reviewed", "safe_to_retry_install_only"),
}
ORDER = ("recovery", "backup", "restore", "prepared")
MAX_AGE = 24 * 60 * 60
DMI_UUID = Path("/sys/class/dmi/id/product_uuid")
INSTALL_LOCK = Path("/run/lock/luxnix-boot-install.lock")
HOST = re.compile(r"[a-z][a-z0-9-]{0,62}")
CLOSURE = re.compile(r"/nix/store/[a-z0-9]{32}-nixos-system-[^/]+")


class MigrationError(ValueError):
    pass


def run(*args: str, timeout: int = 120) -> str:
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        # Never relay subprocess diagnostics which may include private metadata.
        raise MigrationError(
            f"{Path(args[0]).name} failed (exit {result.returncode}); no next "
            f"step was started"
        )
    return result.stdout.strip()


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def exact_keys(value: dict, keys: set[str], name: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise MigrationError(f"{name} has missing or unknown fields")


def private_path(path: Path, *, directory: bool = False) -> None:
    if not path.is_absolute() or path.resolve() != path:
        raise MigrationError("Use an absolute private path without symbolic links")
    for parent in path.parents:
        if parent.stat().st_mode & 0o022:
            raise MigrationError("Evidence path has a parent writable by another user")
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise MigrationError(
            "Evidence and state must belong to the current operator and be "
            "private (0700 directories, 0600 files)"
        )
    encrypted_storage(path)


@contextmanager
def locked_state(state: Path, *, create: bool = False):
    if create and not state.exists():
        private_path(state.parent, directory=True)
        state.mkdir(mode=0o700)
    private_path(state, directory=True)
    fd = os.open(
        state / ".lock",
        os.O_RDWR | (os.O_CREAT if create else 0) | os.O_NOFOLLOW,
        0o600,
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            raise MigrationError("Unsafe operation lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise MigrationError(
                "Another operation is using this plan; wait for it to finish"
            ) from error
        yield
    finally:
        os.close(fd)


def source_identity(checkout: Path) -> dict:
    if (
        not checkout.is_absolute()
        or checkout.resolve() != checkout
        or checkout == Path("/tmp")
        or Path("/tmp") in checkout.parents
    ):
        raise MigrationError(
            "Use a durable reviewed checkout outside /tmp without symbolic links"
        )
    if run(
        "git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=normal"
    ):
        raise MigrationError(
            "The release checkout has uncommitted changes; review and retain "
            "a clean release first"
        )
    return {
        "revision": run("git", "-C", str(checkout), "rev-parse", "HEAD"),
        "lock_sha256": file_digest(checkout / "flake.lock"),
    }


def evaluate(checkout: Path, host: str) -> dict:
    expression = """let f = builtins.getFlake CHECKOUT;
      c = f.nixosConfigurations.HOST.config;
    in { host = c.networking.hostName;
      layout = c.luxnix.storage.operatorUnlocked.layout;
      enabled = c.luxnix.storage.operatorUnlocked.enable;
      closure = builtins.toString c.system.build.toplevel;
      disks = builtins.mapAttrs (_: d: d.device) c.disko.devices.disk;
      mounts = builtins.mapAttrs
        (_: v: { inherit (v) device fsType options; }) c.fileSystems;
      crypttab = c.environment.etc.crypttab.text or "";
      deferred_protected =
        !c.luxnix.storage.operatorUnlocked.autoStartProtectedServices;
      protected_mounts = (map (v: v.mountPoint)
        (builtins.attrValues c.luxnix.storage.operatorUnlocked.volumes))
        ++ builtins.attrNames c.luxnix.storage.operatorUnlocked.bindMounts;
      secure_boot = c.system.boot.secureBoot;
      remote_unlock = c.luxnix.storage.operatorUnlocked.remoteUnlock;
      admin = let name = c.user.admin.name; u = c.users.users.${name}; in {
        inherit name; hash_file = u.hashedPasswordFile;
        source = c.luxnix.storage.operatorUnlocked.migration
          .accountHashes.${u.hashedPasswordFile} or null;
        keys = u.openssh.authorizedKeys.keys;
        wheel = builtins.elem "wheel" u.extraGroups;
        normal = u.isNormalUser;
      };
      failures = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
    }""".replace("CHECKOUT", json.dumps("git+file://" + str(checkout))).replace(
        "HOST", host
    )
    result = json.loads(
        run(
            "nix",
            "eval",
            "--no-update-lock-file",
            "--impure",
            "--json",
            "--expr",
            expression,
            timeout=600,
        )
    )
    if (
        result["host"] != host
        or not result["enabled"]
        or result["layout"] != "boot-luks"
        or result["failures"]
    ):
        raise MigrationError(
            "The reviewed host must evaluate without assertions and select "
            "boot-luks; legacy maintenance is a separate workflow"
        )
    if not CLOSURE.fullmatch(result["closure"]):
        raise MigrationError("Unexpected system closure path")
    return result


def fresh_install(spec: dict) -> bool:
    return spec.get("installation", "migration") == "fresh"


def stage_order(plan: dict) -> tuple[str, ...]:
    return ("recovery", "prepared") if fresh_install(plan["spec"]) else ORDER


def validate_selection(spec: dict, config: dict) -> None:
    if spec.get("root_encryption", "luks2") != "luks2":
        raise MigrationError("New installations require root_encryption: luks2")
    if config.get("layout") != "boot-luks":
        raise MigrationError(
            "Root encryption selection differs from the reviewed host; "
            "create a matching explicit plan"
        )


def validate_spec(spec: dict) -> None:
    optional = (
        set(spec) & {"root_encryption", "installation"}
        if isinstance(spec, dict)
        else set()
    )
    exact_keys(
        spec,
        {
            "schema_version",
            "host",
            "checkout",
            "hardware_uuid",
            "source_retention",
            "disks",
        }
        | optional,
        "Operator specification",
    )
    if (
        spec["schema_version"] != 1
        or not isinstance(spec["host"], str)
        or not HOST.fullmatch(spec["host"])
    ):
        raise MigrationError("Unsupported specification version or host name")
    if spec.get("root_encryption", "luks2") != "luks2":
        raise MigrationError("New installations require root_encryption: luks2")
    if spec.get("installation", "migration") not in {"migration", "fresh"}:
        raise MigrationError("Select installation: migration or fresh")
    retention = (
        {"new-disks"} if fresh_install(spec) else {"old-disks", "whole-disk-image"}
    )
    if spec["source_retention"] not in retention:
        raise MigrationError(
            "Fresh installation requires new-disks; migration requires old-disks "
            "or whole-disk-image retention"
        )
    if not isinstance(spec["hardware_uuid"], str) or not re.fullmatch(
        r"[a-fA-F0-9-]{36}", spec["hardware_uuid"]
    ):
        raise MigrationError(
            "Record the target hardware DMI UUID from its trusted inventory"
        )
    if not isinstance(spec["disks"], list) or not spec["disks"]:
        raise MigrationError("Select the exact target disks")
    for disk in spec["disks"]:
        exact_keys(disk, {"path", "serial", "size_bytes"}, "Disk selection")
        if (
            not isinstance(disk["path"], str)
            or not disk["path"].startswith("/dev/disk/by-id/")
            or "/" in disk["path"].removeprefix("/dev/disk/by-id/")
            or not isinstance(disk["serial"], str)
            or not disk["serial"].strip()
            or type(disk["size_bytes"]) is not int
            or disk["size_bytes"] <= 0
        ):
            raise MigrationError(
                "Every disk needs a stable by-id path, exact serial and byte size"
            )
    if len({d["path"] for d in spec["disks"]}) != len(spec["disks"]) or len(
        {d["serial"] for d in spec["disks"]}
    ) != len(spec["disks"]):
        raise MigrationError("Duplicate target disk identity")


def create_plan(spec_path: Path, state: Path) -> dict:
    private_path(spec_path)
    spec = yaml.safe_load(spec_path.read_text())
    validate_spec(spec)
    with locked_state(state, create=True):
        if (state / "plan.json").exists():
            existing = load_plan(state)
            if existing["spec"] != spec:
                raise MigrationError(
                    "This plan is immutable; use a new private state "
                    "directory for a different target or release"
                )
            verify_source(existing)
            if not (state / "progress.json").exists():
                raise MigrationError(
                    "Plan initialization was interrupted; retain this "
                    "directory and create a new private state directory"
                )
            load_progress(state, existing)
            return existing
        source = source_identity(Path(spec["checkout"]))
        config = evaluate(Path(spec["checkout"]), spec["host"])
        validate_selection(spec, config)
        if config["secure_boot"]:
            raise MigrationError(
                "Controller-signed first installation is not supported by "
                "this installer gate; do not disable Secure Boot to bypass it"
            )
        if set(config["disks"].values()) != {d["path"] for d in spec["disks"]}:
            raise MigrationError(
                "Selected disks do not exactly match the evaluated host layout"
            )
        built = run(
            "nix",
            "build",
            "--no-update-lock-file",
            "--no-link",
            "--print-out-paths",
            str(spec["checkout"])
            + "#nixosConfigurations."
            + spec["host"]
            + ".config.system.build.toplevel",
            timeout=3600,
        )
        if (
            built != config["closure"]
            or source_identity(Path(spec["checkout"])) != source
        ):
            raise MigrationError("Release changed during build; no plan was published")
        payload = {
            "schema_version": 1,
            "spec": spec,
            "source": source,
            "config": config,
        }
        plan = payload | {"plan_id": digest(payload)}
        atomic_json(state / "plan.json", plan)
        atomic_json(
            state / "progress.json",
            {
                "plan_id": plan["plan_id"],
                "attestations": {},
                "install": {"status": "pending"},
            },
        )
        return plan


def load_plan(state: Path) -> dict:
    private_path(state / "plan.json")
    plan = json.loads((state / "plan.json").read_text())
    exact_keys(plan, {"schema_version", "spec", "source", "config", "plan_id"}, "Plan")
    if plan["schema_version"] != 1 or plan["plan_id"] != digest(
        {k: v for k, v in plan.items() if k != "plan_id"}
    ):
        raise MigrationError("Plan content changed; do not reuse its evidence")
    validate_spec(plan["spec"])
    return plan


def load_progress(state: Path, plan: dict) -> dict:
    private_path(state / "progress.json")
    progress = json.loads((state / "progress.json").read_text())
    exact_keys(progress, {"plan_id", "attestations", "install"}, "Progress")
    if progress["plan_id"] != plan["plan_id"] or not isinstance(
        progress["attestations"], dict
    ):
        raise MigrationError("Progress belongs to another plan")
    if progress["install"].get("status") not in {
        "pending",
        "running",
        "interrupted",
        "complete",
    }:
        raise MigrationError("Unknown install state; retain evidence for review")
    return progress


def verify_source(plan: dict) -> None:
    if source_identity(Path(plan["spec"]["checkout"])) != plan["source"]:
        raise MigrationError(
            "The reviewed release or lockfile changed; create a new plan"
        )


def required_checks(stage: str, plan: dict) -> set[str]:
    if stage in ORDER and stage not in stage_order(plan):
        raise MigrationError("This stage does not apply to a fresh installation")
    required = set(STAGES[stage])
    if fresh_install(plan["spec"]):
        if stage == "recovery":
            required = {
                "console_boot_tested",
                "trusted_installer_tested",
                "independent_credentials_tested",
                "new_disks_verified",
            }
        elif stage == "prepared":
            required -= {"database_restored", "identities_restored"}
            required.add("initial_credentials_staged")
    if stage == "backup" and plan["spec"]["source_retention"] == "whole-disk-image":
        required.add("whole_disk_image_verified")
    return required


def check_attestation(
    stage: str, plan: dict, progress: dict, *, fresh: bool = True
) -> None:
    record = progress["attestations"].get(stage)
    if not record or record["plan_id"] != plan["plan_id"]:
        raise MigrationError(
            f"Stop: the {stage} step needs a named operator assessment"
        )
    age = time.time() - record["recorded_at"]
    if fresh and not 0 <= age <= MAX_AGE:
        raise MigrationError(
            f"The {stage} assessment is older than 24 hours or has an invalid "
            f"clock; reassess it"
        )
    exact_keys(
        record,
        {"plan_id", "kind", "assessor", "recorded_at", "artifacts", "checks"},
        "Assessment",
    )
    if (
        record["kind"] != "human-attestation"
        or set(record["checks"]) != required_checks(stage, plan)
        or not record["artifacts"]
    ):
        raise MigrationError("Invalid human assessment")
    for artifact in record["artifacts"]:
        path = Path(artifact["path"])
        private_path(path)
        if file_digest(path) != artifact["sha256"]:
            raise MigrationError(
                f"The {stage} evidence changed; reassess this step and all "
                f"following steps"
            )
    if stage == "recovery" and not fresh_install(plan["spec"]):
        verify_readiness(record["artifacts"], plan, fresh=fresh)


def attest(state: Path, stage: str, evidence_path: Path, assessor: str) -> None:
    if (
        not assessor.strip()
        or len(assessor) > 200
        or any(ord(c) < 32 for c in assessor)
    ):
        raise MigrationError(
            "Name the person who actually performed or reviewed these checks"
        )
    with locked_state(state):
        plan = load_plan(state)
        progress = load_progress(state, plan)
        verify_source(plan)
        private_path(evidence_path)
        evidence = json.loads(evidence_path.read_text())
        exact_keys(
            evidence,
            {"schema_version", "plan_id", "stage", "checks", "artifacts"},
            "Human evidence",
        )
        if (
            evidence["schema_version"] != 1
            or evidence["plan_id"] != plan["plan_id"]
            or evidence["stage"] != stage
        ):
            raise MigrationError("Evidence does not name this exact plan and step")
        checks = required_checks(stage, plan)
        if (
            not isinstance(evidence["checks"], dict)
            or set(evidence["checks"]) != checks
            or any(v is not True for v in evidence["checks"].values())
        ):
            raise MigrationError(
                "Every required check needs an explicit successful human assessment: "
                + ", ".join(sorted(checks))
            )
        if (
            not isinstance(evidence["artifacts"], list)
            or not evidence["artifacts"]
            or any(not isinstance(p, str) for p in evidence["artifacts"])
        ):
            raise MigrationError(
                "Attach private evidence reports or manifests; an assertion "
                "without evidence is insufficient"
            )
        order = stage_order(plan)
        if stage in order:
            for prior in order[: order.index(stage)]:
                check_attestation(prior, plan, progress)
        elif stage == "acceptance" and progress["install"]["status"] != "complete":
            raise MigrationError(
                "Complete installation before recording physical acceptance"
            )
        elif (
            stage == "install-recovery"
            and progress["install"]["status"] != "interrupted"
        ):
            raise MigrationError("There is no interrupted installation to review")
        artifacts = []
        for path in dict.fromkeys([str(evidence_path), *evidence["artifacts"]]):
            private_path(Path(path))
            artifacts.append({"path": path, "sha256": file_digest(Path(path))})
        if stage == "recovery" and not fresh_install(plan["spec"]):
            verify_readiness(artifacts, plan)
        previous = progress["attestations"].get(stage)
        if (
            previous
            and previous["artifacts"] == artifacts
            and previous["assessor"] == assessor
        ):
            check_attestation(stage, plan, progress)
            return
        if progress["install"]["status"] == "complete" and stage != "acceptance":
            raise MigrationError(
                "Completed installation evidence is immutable; create a new "
                "plan for a new operation"
            )
        if stage in order:
            for later in order[order.index(stage) + 1 :]:
                progress["attestations"].pop(later, None)
            progress["attestations"].pop("install-recovery", None)
        progress["attestations"][stage] = {
            "plan_id": plan["plan_id"],
            "kind": "human-attestation",
            "assessor": assessor,
            "recorded_at": time.time(),
            "artifacts": artifacts,
            "checks": sorted(checks),
        }
        atomic_json(state / "progress.json", progress)


def verify_readiness(artifacts: list[dict], plan: dict, *, fresh: bool = True) -> None:
    from lx_administration.storage.readiness import evaluate as admit

    reports = []
    for artifact in artifacts:
        path = Path(artifact["path"])
        # Reports are small JSON documents, never decrypt or parse backup payloads.
        if path.suffix != ".json" or path.stat().st_size > 2 * 1024 * 1024:
            continue
        value = json.loads(path.read_text())
        if isinstance(value, dict) and "report_sha256" in value:
            reports.append(value)
    if len(reports) != 1:
        raise MigrationError(
            "Recovery evidence must include exactly one private readiness "
            "admission JSON report captured through pinned SSH"
        )
    report = reports[0]
    payload = {
        k: v for k, v in report.items() if k not in {"report_sha256", "admission"}
    }
    admission = report.get("admission", {})
    if report["report_sha256"] != digest(payload):
        raise MigrationError(
            "Readiness report content does not match its recorded digest"
        )
    decision = admit(
        report,
        plan["spec"]["host"],
        admission.get("expected_layout"),
        admission.get("expected_serials"),
    )
    if not decision["admitted"]:
        raise MigrationError(
            "The readiness baseline fails admission; collect a corrected "
            "report before proceeding"
        )
    observed = datetime.fromisoformat(report["observed_at"])
    if observed.tzinfo is None or (
        fresh and not 0 <= time.time() - observed.timestamp() <= MAX_AGE
    ):
        raise MigrationError(
            "Readiness observation must be from the last 24 hours with an "
            "explicit timezone"
        )


@contextmanager
def installer_lock():
    if os.geteuid() != 0:
        raise MigrationError(
            "Run the install-only action as root from trusted installer media"
        )
    fd = os.open(INSTALL_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise MigrationError("Unsafe global installer lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise MigrationError(
                "Another installer operation is active on this machine"
            ) from error
        # The child retains this lock if the controller process terminates.
        yield fd
    finally:
        os.close(fd)


def verify_independent_state(state: Path, progress: dict, disks: set[int]) -> None:
    paths = [
        state,
        *(
            Path(a["path"])
            for r in progress["attestations"].values()
            for a in r["artifacts"]
        ),
    ]
    for path in paths:
        mount = json.loads(
            run(
                "findmnt",
                "--json",
                "--target",
                str(path),
                "--output",
                "SOURCE,FSTYPE,UUID",
            )
        )["filesystems"][0]
        source = mount["source"].split("[", 1)[0]
        members = filesystem_devices(mount)
        if not source.startswith("/dev/") or any(
            device_disks(m) & disks for m in members
        ):
            raise MigrationError(
                "Keep the plan and every evidence file on independent "
                "encrypted storage, outside all target disks"
            )


def walk(devices: list[dict]):
    for device in devices:
        yield device
        yield from walk(device.get("children", []))


def probe_disks(plan: dict) -> set[int]:
    if DMI_UUID.read_text().strip().lower() != plan["spec"]["hardware_uuid"].lower():
        raise MigrationError(
            "This is not the hardware selected by the operator; no install will run"
        )
    devices = set()
    for disk in plan["spec"]["disks"]:
        rows = json.loads(
            run(
                "lsblk",
                "--json",
                "--bytes",
                "--nodeps",
                "--output",
                "PATH,TYPE,SERIAL,SIZE",
                disk["path"],
            )
        )["blockdevices"]
        if (
            len(rows) != 1
            or rows[0]["type"] != "disk"
            or rows[0]["serial"] != disk["serial"]
            or int(rows[0]["size"]) != disk["size_bytes"]
        ):
            raise MigrationError(
                "A target disk serial or size differs from the plan; stop and "
                "review the hardware"
            )
        info = os.stat(disk["path"])
        if not stat.S_ISBLK(info.st_mode) or info.st_rdev in devices:
            raise MigrationError(
                "Target disks are missing, aliased or not block devices"
            )
        devices.add(info.st_rdev)
    return devices


def device_disks(device: str) -> set[int]:
    tree = json.loads(
        run("lsblk", "--json", "--paths", "--inverse", "--output", "NAME,TYPE", device)
    )["blockdevices"]
    disks = {os.stat(d["name"]).st_rdev for d in walk(tree) if d["type"] == "disk"}
    if not disks:
        raise MigrationError(
            "Unable to identify physical disks for a mounted filesystem"
        )
    return disks


def mount_record(path: str) -> dict:
    rows = json.loads(
        run(
            "findmnt",
            "--json",
            "--mountpoint",
            path,
            "--output",
            "SOURCE,FSTYPE,UUID,FSROOT",
        )
    )["filesystems"]
    if len(rows) != 1:
        raise MigrationError(f"Required mount is missing or ambiguous: {path}")
    return rows[0]


def verify_installer(disks: set[int]) -> None:
    if os.geteuid() != 0:
        raise MigrationError(
            "Installation checks must run as root on the selected machine "
            "from trusted recovery media"
        )
    current = mount_record("/")
    if current["fstype"] not in {"tmpfs", "overlay", "squashfs"}:
        raise MigrationError(
            "The running root is not a live recovery environment; boot the "
            "tested installer first"
        )
    # A selected target must never be the backing store of the running installer.
    store = json.loads(
        run("findmnt", "--json", "--target", "/nix/store", "--output", "SOURCE")
    )["filesystems"][0]["source"].split("[", 1)[0]
    if store.startswith("/dev/") and device_disks(store) & disks:
        raise MigrationError(
            "The installer is using a target disk; boot independent recovery media"
        )
    if run("swapon", "--show", "--noheadings", "--output", "NAME"):
        raise MigrationError("Disable installer swap before handling restored secrets")


def verify_target(plan: dict, disks: set[int]) -> dict:
    # Reuse the same mount, Btrfs member, LUKS2 and key checks used at runtime.
    from lx_administration.storage import boot

    identities = {}
    for mount, expected in plan["config"]["mounts"].items():
        if not mount.startswith("/") or ".." in Path(mount).parts:
            raise MigrationError("Unsafe evaluated mountpoint")
        path = "/mnt" + (mount if mount != "/" else "")
        if Path(path).resolve() != Path(path):
            raise MigrationError("A prepared target mount contains a symbolic link")
        record = mount_record(path)
        source = record["source"].split("[", 1)[0]
        if expected["fsType"] == "tmpfs":
            if record["fstype"] != "tmpfs":
                raise MigrationError("Unexpected temporary filesystem")
            continue
        expected_device = expected["device"]
        if not expected_device.startswith("/dev/"):
            expected_device = "/mnt" + expected_device
        if mount == "/boot":
            if (
                record["fstype"] != "vfat"
                or os.stat(source).st_rdev != os.stat(expected_device).st_rdev
            ):
                raise MigrationError("Wrong EFI filesystem")
        else:
            subvolume = next(
                (o for o in expected["options"] if o.startswith("subvol=")), None
            )
            boot.verify_mount(
                path,
                expected_device,
                None if expected["fsType"] == "none" else expected["fsType"],
                subvolume,
            )
        if not device_disks(source) <= disks:
            raise MigrationError(
                "A prepared mount uses a disk outside the operator selection"
            )
        if any(
            not device_disks(member) <= disks
            for member in filesystem_devices(record)
        ):
            raise MigrationError(
                "A filesystem member is outside the selected target disks"
            )
        identities[mount] = {
            "uuid": record["uuid"],
            "fsroot": record.get("fsroot"),
            "source": source,
        }
    if "/" not in identities or "/boot" not in identities:
        raise MigrationError("The complete root and EFI mount graph is required")
    for line in plan["config"]["crypttab"].splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 4 or not fields[2].startswith("/etc/luks-keys/"):
            raise MigrationError("Unexpected secondary-key contract")
        key = "/mnt" + fields[2]
        boot.verify_unlock({"path": key, "device": fields[1], "mapping": fields[0]})
        if not device_disks(fields[1]) <= disks:
            raise MigrationError("A secondary key targets a disk outside the plan")
    verify_accounts(plan)
    if plan["config"].get("remote_unlock", {}).get("enable"):
        verify_unlock_identity(plan)
    return identities


def target_private(
    path: str, root: Path = Path("/mnt"), *, encrypted: bool = True
) -> Path:
    if (
        not path.startswith("/")
        or ".." in Path(path).parts
        or path.startswith("/nix/store/")
    ):
        raise MigrationError("Invalid restored access credential path")
    target = root / path.lstrip("/")
    if target.resolve() != target:
        raise MigrationError("Restored access credentials must not use symbolic links")
    if encrypted:
        encrypted_storage(target)
    info = target.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)
    ):
        raise MigrationError(
            "Restored access credentials require root ownership and mode 0400 or 0600"
        )
    return target


def account_hash(path: Path) -> bytes:
    from lx_administration.storage import operator_migration

    try:
        return operator_migration.account_hash(path)
    except operator_migration.MigrationError as exc:
        raise MigrationError("Restored administrator hash is missing, locked, malformed or retired") from exc


def verify_accounts(plan: dict, root: Path = Path("/mnt")) -> None:
    admin = plan["config"].get("admin")
    if not admin or not admin["normal"] or not admin["wheel"] or not admin["hash_file"]:
        raise MigrationError(
            "Plan must contain an evaluated normal administrator account "
            "with sudo access and a password file"
        )
    credential = target_private(admin["hash_file"], root)
    account_hash(credential)
    if not admin["keys"] or not all(
        isinstance(k, str) and "\n" not in k for k in admin["keys"]
    ):
        raise MigrationError(
            "The reviewed administrator must retain explicit SSH public keys"
        )


def verify_unlock_identity(plan: dict, root: Path = Path("/mnt")) -> str:
    path = target_private(plan["config"]["remote_unlock"]["hostKey"], root)
    public = run("ssh-keygen", "-y", "-P", "", "-f", str(path))
    if not public.startswith("ssh-ed25519 "):
        raise MigrationError(
            "Early-boot SSH must use its dedicated Ed25519 host identity"
        )
    return public


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def prepare_access(state: Path, root: Path = Path("/mnt")) -> dict:
    """Restore a missing boot hash and create only the dedicated SSH host identity."""
    import tempfile

    with installer_lock(), locked_state(state):
        plan = load_plan(state)
        progress = load_progress(state, plan)
        disks = check_gates(plan, progress, "provision")
        verify_independent_state(state, progress, disks)
        from lx_administration.storage import boot

        root_config = plan["config"]["mounts"]["/"]
        root_device = "/dev/mapper/cryptroot"
        boot.verify_mount(str(root), root_device, root_config["fsType"])
        if not device_disks(root_device) <= disks:
            raise MigrationError("Prepared root is outside the selected disks")
        admin = plan["config"].get("admin")
        if not admin or not admin["hash_file"]:
            raise MigrationError(
                "Create a new plan containing the evaluated administrator contract"
            )
        target = root / admin["hash_file"].lstrip("/")
        changed = False
        if not target.exists():
            if not admin["source"]:
                raise MigrationError(
                    "No restored authoritative administrator hash source is configured"
                )
            content = account_hash(target_private(admin["source"], root))
            parent = target.parent
            if parent.resolve() != parent:
                raise MigrationError("Unsafe administrator credential directory")
            encrypted_storage(parent)
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            sync_directory(parent)
            changed = True
        verify_accounts(plan, root)
        remote = plan["config"].get("remote_unlock", {})
        public = None
        if remote.get("enable"):
            if remote["hostKey"] != "/etc/luxnix/initrd-ssh/ssh_host_ed25519_key":
                raise MigrationError("Refusing a non-dedicated SSH host key path")
            key = root / remote["hostKey"].lstrip("/")
            if not key.exists():
                if key.parent.resolve() != key.parent:
                    raise MigrationError("Unsafe SSH identity directory")
                encrypted_storage(key.parent)
                key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(
                    prefix=".prepare-", dir=key.parent
                ) as directory:
                    temporary = Path(directory) / "host-key"
                    run(
                        "ssh-keygen",
                        "-q",
                        "-t",
                        "ed25519",
                        "-N",
                        "",
                        "-f",
                        str(temporary),
                    )
                    # Publish exclusively; never replace an existing identity.
                    with temporary.open("rb") as stream:
                        os.fsync(stream.fileno())
                    os.link(temporary, key)
                    sync_directory(key.parent)
                    changed = True
            public = verify_unlock_identity(plan, root)
        return {
            "changed": changed,
            "host": plan["spec"]["host"],
            "unlock_host_public_key": public,
            "next": (
                "Pin this public host key on the operator computer before "
                "the first remote unlock. Existing credentials were never replaced."
            ),
        }


def check_gates(plan: dict, progress: dict, stage: str) -> set[int]:
    verify_source(plan)
    validate_selection(plan["spec"], plan["config"])
    order = stage_order(plan)
    for prior in order[:-1] if stage == "provision" else order:
        check_attestation(prior, plan, progress)
    if plan["config"]["secure_boot"]:
        raise MigrationError(
            "Signed first installation needs a supported controller-signing "
            "workflow; do not downgrade Secure Boot"
        )
    disks = probe_disks(plan)
    verify_installer(disks)
    return disks


def verify_unmounted_targets(plan: dict) -> None:
    for disk in plan["spec"]["disks"]:
        tree = json.loads(
            run(
                "lsblk",
                "--json",
                "--paths",
                "--output",
                "NAME,TYPE,MOUNTPOINTS,FSTYPE",
                disk["path"],
            )
        )["blockdevices"]
        if fresh_install(plan["spec"]) and any(d.get("fstype") for d in walk(tree)):
            raise MigrationError(
                "Fresh installation requires empty new disks; "
                "existing filesystems need a migration plan"
            )
        if any(
            d["type"] == "crypt" or any(d.get("mountpoints") or []) for d in walk(tree)
        ):
            raise MigrationError(
                "A selected disk still has an open mapping or mounted "
                "filesystem; provisioning preconditions fail"
            )


def check(state: Path, stage: str) -> dict:
    with locked_state(state):
        plan = load_plan(state)
        progress = load_progress(state, plan)
        disks = check_gates(plan, progress, stage)
        verify_independent_state(state, progress, disks)
        if stage == "install":
            verify_target(plan, disks)
        else:
            verify_unmounted_targets(plan)
        return {
            "plan_id": plan["plan_id"],
            "host": plan["spec"]["host"],
            "stage": stage,
            "checks_passed": True,
            "effect": "No disk changes. This check does not authorize formatting.",
        }


def confirm(plan: dict) -> None:
    if not sys.stdin.isatty():
        raise MigrationError(
            "Installation needs the operator at an interactive terminal; "
            "unattended approval is not supported"
        )
    phrase = "INSTALL " + plan["spec"]["host"] + " " + plan["plan_id"][:12]
    print(
        "Install the reviewed system onto the prepared disks. Existing boot "
        "settings will change."
    )
    print(
        "This does not format disks or restore data. Keep the old disks and "
        "recovery copies."
    )
    print(
        "A previous NixOS generation cannot reverse disk formatting or "
        "recover lost keys."
    )
    print("Selected disks: " + ", ".join(d["serial"] for d in plan["spec"]["disks"]))
    if input("To proceed, type " + phrase + ": ").strip() != phrase:
        raise MigrationError("Installation cancelled; no install command ran")


def install(state: Path, *, retry_interrupted: bool = False) -> None:
    with installer_lock() as install_lock, locked_state(state):
        plan = load_plan(state)
        progress = load_progress(state, plan)
        status = progress["install"]["status"]
        if status == "complete":
            # Never repeat mutation when an existing successful result is present.
            print(
                "Installation already completed for this plan. Physical "
                "cold-boot acceptance is a separate step."
            )
            return
        if status == "interrupted" or status == "running":
            if status == "running":
                progress["install"]["status"] = "interrupted"
                atomic_json(state / "progress.json", progress)
            if not retry_interrupted:
                raise MigrationError(
                    "A previous installation may have changed boot state. "
                    "Review it and record install-recovery evidence before an "
                    "explicit retry"
                )
            check_attestation("install-recovery", plan, progress)
        elif retry_interrupted:
            raise MigrationError("There is no interrupted installation to retry")
        disks = check_gates(plan, progress, "install")
        verify_independent_state(state, progress, disks)
        identities = verify_target(plan, disks)
        previous = progress["install"].get("mounts")
        if previous is not None and previous != identities:
            raise MigrationError(
                "Prepared filesystem identities changed after the first "
                "install attempt; do not reuse this plan"
            )
        if not Path(plan["config"]["closure"]).is_dir():
            raise MigrationError(
                "The reviewed built closure is not available in the installer store"
            )
        confirm(plan)
        # Recheck after the operator prompt, immediately before the one mutation.
        if (
            check_gates(plan, progress, "install") != disks
            or verify_target(plan, disks) != identities
        ):
            raise MigrationError("Target changed while awaiting confirmation")
        verify_independent_state(state, progress, disks)
        progress["attestations"].pop("install-recovery", None)
        progress["install"] = {
            "status": "running",
            "mounts": identities,
            "started_at": time.time(),
        }
        atomic_json(state / "progress.json", progress)
        try:
            subprocess.run(
                [
                    "nixos-install",
                    "--root",
                    "/mnt",
                    "--system",
                    plan["config"]["closure"],
                    "--no-root-passwd",
                ],
                check=True,
                pass_fds=(install_lock,),
            )
            link = Path("/mnt/nix/var/nix/profiles/system")
            # Absolute store symlinks resolve in the live installer as the same closure.
            if str(link.resolve()) != plan["config"]["closure"]:
                raise MigrationError(
                    "Installed system profile does not match the reviewed closure"
                )
            if verify_target(plan, disks) != identities:
                raise MigrationError("Target identity changed during installation")
        except BaseException:
            progress["install"]["status"] = "interrupted"
            atomic_json(state / "progress.json", progress)
            raise
        progress["install"]["status"] = "complete"
        progress["install"]["finished_at"] = time.time()
        atomic_json(state / "progress.json", progress)
        print(
            "Installation completed. Do not remove recovery copies; perform "
            "the separate cold-boot acceptance checks."
        )


def status(state: Path) -> dict:
    with locked_state(state):
        plan = load_plan(state)
        progress = load_progress(state, plan)
        assessments = {}
        for stage in (*stage_order(plan), "acceptance"):
            try:
                check_attestation(
                    stage,
                    plan,
                    progress,
                    fresh=progress["install"]["status"] != "complete",
                )
                assessments[stage] = "human evidence recorded; not automated proof"
            except (ValueError, OSError) as error:
                assessments[stage] = str(error)
        return {
            "host": plan["spec"]["host"],
            "plan_id": plan["plan_id"],
            "install": progress["install"]["status"],
            "assessments": assessments,
            "root_encryption": plan["spec"].get("root_encryption", "luks2"),
            "installation": plan["spec"].get("installation", "migration"),
            "required_checks": {
                s: sorted(required_checks(s, plan))
                for s in (*stage_order(plan), "acceptance", "install-recovery")
            },
            "note": "No formatting, activation, reboot or cleanup is "
            "performed by this workflow.",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser(
        "plan",
        help="Build a reviewed release and create an immutable private plan; "
        "no target access",
    )
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    for name in ("status", "attest", "check", "install", "prepare-access"):
        p = sub.add_parser(name)
        p.add_argument("--state", type=Path, required=True)
        if name == "attest":
            p.add_argument("--stage", choices=STAGES, required=True)
            p.add_argument("--evidence", type=Path, required=True)
            p.add_argument("--assessor", required=True)
        if name == "check":
            p.add_argument("--stage", choices=["provision", "install"], required=True)
        if name == "install":
            p.add_argument("--retry-interrupted", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.action == "plan":
            plan = create_plan(args.spec, args.state)
            print(
                json.dumps(
                    {
                        "host": plan["spec"]["host"],
                        "plan_id": plan["plan_id"],
                        "root_encryption": plan["spec"].get("root_encryption", "luks2"),
                        "installation": plan["spec"].get("installation", "migration"),
                        "next": "Review recovery evidence; no production "
                        "action was performed.",
                    }
                )
            )
        elif args.action == "attest":
            attest(args.state, args.stage, args.evidence, args.assessor)
            print(
                "Human assessment recorded. It is not automated proof of "
                "restore or recovery."
            )
        elif args.action == "check":
            print(json.dumps(check(args.state, args.stage), indent=2))
        elif args.action == "prepare-access":
            print(json.dumps(prepare_access(args.state), indent=2))
        elif args.action == "install":
            install(args.state, retry_interrupted=args.retry_interrupted)
        else:
            print(json.dumps(status(args.state), indent=2))
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        EOFError,
        KeyboardInterrupt,
        subprocess.SubprocessError,
        yaml.YAMLError,
    ) as error:
        parser.exit(
            1,
            f"Stop: {error}. Keep the current disks and recovery copies; "
            f"review the migration runbook.\n",
        )


if __name__ == "__main__":
    main()
