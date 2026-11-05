"""Sequential root setup: preview by default, confirmed provisioning, no auto-retry."""

from __future__ import annotations

import argparse
from enum import StrEnum
import json
import os
from pathlib import Path
import re
import shlex
import socket
import stat
import subprocess
import sys
from typing import Literal, TextIO
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml

from lx_administration.autoconf.config import AutoconfConfig, DEFAULT_CONFIG_PATH
from lx_administration.storage import boot_migration as migration
from lx_administration.utils.file_operations import (
    atomic_create_file,
    atomic_write_file,
)
from lx_administration.yaml import load_unique_yaml_file


class Phase(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETE = "complete"


class Action(StrEnum):
    ASSESS = "assess"
    PREPARE = "prepare"
    PROVISION = "provision"
    RECOVER = "recover"
    PREPARE_ACCESS = "prepare-access"
    INSTALL = "install"
    INSTALL_RECOVERY = "install-recovery"
    ACCEPT = "acceptance"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlockDevice(Contract):
    path: str
    type: str
    size: int = Field(ge=0, strict=True)
    serial: str | None
    fstype: str | None
    uuid: str | None
    mountpoints: list[str | None]
    children: list[BlockDevice] = Field(default_factory=list)


class DiskTree(Contract):
    blockdevices: list[BlockDevice] = Field(min_length=1, max_length=1)


class MountIdentity(Contract):
    uuid: str | None
    fsroot: str | None
    source: str


class Journal(Contract):
    schema_version: Literal[1] = 1
    plan_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    phase: Phase = Phase.PLANNED
    before: list[BlockDevice] = Field(default_factory=list)
    mounts: dict[str, MountIdentity] = Field(default_factory=dict)
    recovered_by: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def consistent(self) -> Journal:
        if self.phase != Phase.PLANNED and not self.before:
            raise ValueError("An attempted provision requires its disk snapshot")
        if self.phase == Phase.COMPLETE and not {"/", "/boot"} <= self.mounts.keys():
            raise ValueError("Completed provisioning requires root and EFI identities")
        if self.phase != Phase.COMPLETE and (self.mounts or self.recovered_by):
            raise ValueError("Only completed provisioning can record accepted mounts")
        return self


class NextStep(Contract):
    action: Action
    host: str
    plan_id: str
    reason: str
    required_checks: list[str] = Field(default_factory=list)
    stage: str | None = None


def inspect_disk(path: str, *, children: bool = True) -> BlockDevice:
    tree = DiskTree.model_validate_json(
        migration.run(
            "lsblk",
            "--json",
            "--bytes",
            "--paths",
            *([] if children else ["--nodeps"]),
            "--output",
            "PATH,TYPE,SERIAL,SIZE,FSTYPE,UUID,MOUNTPOINTS",
            path,
        )
    )
    disk = tree.blockdevices[0]
    if disk.type != "disk":
        raise migration.MigrationError("Configured target is not a whole disk")
    return disk


def observe(
    checkout: Path,
    host: str,
    installation: str,
    retention: str,
    *,
    hardware_uuid: str | None = None,
) -> dict:
    """Collect a specification on the target; never select substitute disks."""
    if not migration.HOST.fullmatch(host):
        raise migration.MigrationError("Invalid inventory host name")
    if hardware_uuid is None:
        try:
            hardware_uuid = migration.DMI_UUID.read_text().strip()
        except PermissionError as error:
            raise migration.MigrationError(
                "Read the UUID with sudo cat /sys/class/dmi/id/product_uuid, "
                "then pass --hardware-uuid to observe as your normal user; "
                "do not run Devenv with sudo"
            ) from error
    source = migration.source_identity(checkout)
    config = migration.evaluate(checkout, host)
    disks = []
    for path in config["disks"].values():
        disk = inspect_disk(path, children=False)
        disks.append({"path": path, "serial": disk.serial, "size_bytes": disk.size})
    spec = {
        "schema_version": 1,
        "host": host,
        "checkout": str(checkout),
        "hardware_uuid": hardware_uuid,
        "root_encryption": "luks2",
        "installation": installation,
        "source_retention": retention,
        "disks": disks,
    }
    migration.validate_spec(spec)
    if migration.source_identity(checkout) != source:
        raise migration.MigrationError("Release changed during observation")
    return spec


def journal_path(state: Path) -> Path:
    return state / "provision.json"


def load_journal(state: Path, plan: dict) -> Journal:
    path = journal_path(state)
    migration.private_path(path)
    record = Journal.model_validate_json(path.read_bytes())
    if record.plan_id != plan["plan_id"]:
        raise migration.MigrationError("Provision journal belongs to another plan")
    return record


def save_journal(state: Path, record: Journal, **changes: object) -> Journal:
    # Validate every transition at the persistence boundary, including updates.
    record = Journal.model_validate(record.model_dump() | changes)
    atomic_write_file(
        destination=journal_path(state),
        content=[record.model_dump_json(indent=2).encode() + b"\n"],
        file_mode=0o600,
    )
    print(
        json.dumps(
            {
                "event": "root_provision_journal",
                "plan_id": record.plan_id,
                "phase": record.phase.value,
            }
        ),
        file=sys.stderr,
    )
    return record


def provisioner(plan: dict) -> Path:
    value = plan["config"].get("provisioner", "")
    if not re.fullmatch(r"/nix/store/[a-z0-9]{32}-disko", value):
        raise migration.MigrationError(
            "Create a new plan containing the pinned Disko provisioner"
        )
    path = Path(value)
    link = path.lstat()
    resolved = path.resolve(strict=True)
    if not re.fullmatch(r"/nix/store/[a-z0-9]{32}-disko(?:/bin/disko)?", str(resolved)):
        raise migration.MigrationError(
            "Provisioner resolves outside its store contract"
        )
    info = resolved.lstat()
    if (
        link.st_uid != 0
        or not stat.S_ISREG(info.st_mode)
        or info.st_mode & 0o222
        or info.st_uid != 0
        or migration.file_digest(resolved) != plan["config"].get("provisioner_sha256")
    ):
        raise migration.MigrationError("Pinned provisioner is missing or changed")
    return path


def prepare(state: Path) -> None:
    with migration.locked_state(state):
        plan = migration.load_plan(state)
        migration.verify_source(plan)
        provisioner(plan)
        migration.load_progress(state, plan)
        if journal_path(state).exists():
            load_journal(state, plan)  # Preserve all existing attempt history.
            return
        save_journal(state, Journal(plan_id=plan["plan_id"]))


def snapshot_disks(plan: dict) -> list[BlockDevice]:
    result = []
    for disk in plan["spec"]["disks"]:
        observed = inspect_disk(disk["path"])
        if observed.serial != disk["serial"] or observed.size != disk["size_bytes"]:
            raise migration.MigrationError("Disk snapshot differs from the plan")
        result.append(observed)
    return result


def show_target(spec: dict, *, stream: TextIO | None = None) -> None:
    print(f"\nTARGET COMPUTER: {spec['host']}", file=stream)
    print(
        "Selected disks (check the serial numbers, not just their names):", file=stream
    )
    for disk in spec["disks"]:
        print(
            f"  {disk['path']} | serial={disk['serial']} | "
            f"{disk['size_bytes'] / 1024**3:.1f} GiB ({disk['size_bytes']} bytes)",
            file=stream,
        )
    mode = spec.get("installation", "migration")
    match mode:
        case "disposable":
            message = (
                "DISCARD DATA: installation erases all existing files on these disks. "
                "This plan does NOT require a data backup or restore test. "
                "If you need any existing files or are unsure, STOP and ask an "
                "administrator to prepare a migration plan before continuing."
            )
        case "migration":
            message = (
                "KEEP DATA THROUGH BACKUP AND RESTORE: installation erases these "
                "disks. Required backups, original keys and a tested restore "
                "must be verified first; files are not preserved in place."
            )
        case "fresh":
            message = (
                "NEW DISKS ONLY: stop if any selected disk contains data you need."
            )
        case _:
            raise migration.MigrationError(
                "Unknown installation mode; stop and review the plan"
            )
    print(f"Data policy ({mode}): {message}", file=stream)
    print(
        "No files are backed up by this setup command. Recovery credentials are "
        "required in every mode. A backup for another computer does not count.",
        file=stream,
    )


def confirmation(plan: dict, *, recover: bool = False) -> None:
    verb = "ACCEPT EXISTING LAYOUT" if recover else "ERASE"
    serials = ",".join(d["serial"] for d in plan["spec"]["disks"])
    phrase = f"{verb} {plan['spec']['host']} {plan['plan_id'][:12]} {serials}"
    # A pipe or sudo's password channel cannot supply destructive approval.
    if not sys.stdin.isatty():
        raise migration.MigrationError("Use a private interactive installer terminal")
    with (
        open("/dev/tty", "w", encoding="utf-8") as terminal,
        open("/dev/tty", "r", encoding="utf-8") as response,
    ):
        if not terminal.isatty():
            raise migration.MigrationError("A real controlling terminal is required")
        terminal.write(
            "\n"
            + (
                "Verify the existing layout; no formatter will run.\n"
                if recover
                else "ERASE all contents of the selected disks below.\n"
            )
        )
        show_target(plan["spec"], stream=terminal)
        terminal.write(
            "Old boot generations cannot undo formatting. Keep independent "
            "credentials and recovery media.\nType exactly: " + phrase + "\n> "
        )
        terminal.flush()
        if response.readline().rstrip("\n") != phrase:
            raise migration.MigrationError("Cancelled; no next action ran")


def run_provisioner(path: Path, lock: int) -> None:
    # Inherit the private terminal for Disko's LUKS prompts, never capture keys.
    subprocess.run(
        [str(path)],
        check=True,
        pass_fds=(lock,),
        env={
            "PATH": os.defpath,
            "HOME": "/root",
            "LANG": "C.UTF-8",
            "TERM": os.environ.get("TERM", "dumb"),
        },
    )


def verify_provision_namespace(script: Path, disks: set[int]) -> None:
    # Disko unmounts /mnt and addresses partitions/mappings by global names.
    mounts = json.loads(
        migration.run("findmnt", "--json", "--list", "--output", "TARGET")
    )["filesystems"]
    if any(m["target"] == "/mnt" or m["target"].startswith("/mnt/") for m in mounts):
        raise migration.MigrationError("Unmount /mnt explicitly before provisioning")
    paths = set(
        re.findall(
            r"/dev/(?:disk/by-partlabel|mapper)/[a-zA-Z0-9_.+-]+", script.read_text()
        )
    )
    for path in paths:
        if Path(path).exists():
            owners = migration.device_disks(path)
            if not owners or not owners <= disks:
                raise migration.MigrationError(
                    f"Provisioning name {path} belongs to an unselected disk"
                )


def provision(
    state: Path, *, apply: bool = False, recover_by: str | None = None
) -> None:
    with migration.installer_lock() as lock, migration.locked_state(state):
        plan = migration.load_plan(state)
        migration.verify_source(plan)
        progress = migration.load_progress(state, plan)
        record = load_journal(state, plan)
        if progress["install"]["status"] != "pending":
            raise migration.MigrationError(
                "Installation started; provisioning is closed"
            )
        if record.phase == Phase.COMPLETE:
            print("Provisioning already completed; formatting will not repeat.")
            return
        recovery = recover_by is not None
        if recovery:
            if (
                not recover_by.strip()
                or len(recover_by) > 200
                or any(ord(c) < 32 for c in recover_by)
            ):
                raise migration.MigrationError(
                    "Name the administrator reviewing recovery"
                )
            if record.phase not in {Phase.RUNNING, Phase.INTERRUPTED}:
                raise migration.MigrationError("No uncertain provisioning to recover")
        elif record.phase in {Phase.RUNNING, Phase.INTERRUPTED}:
            raise migration.MigrationError(
                "Provisioning may have changed disks. Never retry the formatter. "
                "Inspect the retained journal and disks; use recover only after "
                "the intended layout is complete, or restore independent recovery."
            )
        disks = migration.check_gates(plan, progress, "provision")
        migration.verify_independent_state(state, progress, disks)
        if recovery:
            identities = migration.verify_layout(plan, disks)
            if not apply:
                print("Existing layout verified; --apply still requires confirmation.")
                return
            confirmation(plan, recover=True)
            if (
                migration.check_gates(plan, progress, "provision") != disks
                or migration.verify_layout(plan, disks) != identities
            ):
                raise migration.MigrationError(
                    "Target changed during recovery approval"
                )
            migration.verify_independent_state(state, progress, disks)
            save_journal(
                state,
                record,
                phase=Phase.COMPLETE,
                mounts=identities,
                recovered_by=recover_by,
            )
            return
        script = provisioner(plan)
        migration.verify_unmounted_targets(plan)
        verify_provision_namespace(script, disks)
        before = snapshot_disks(plan)
        if not apply:
            print(
                "Provision checks passed; no disk writes. "
                "Use --apply for typed approval."
            )
            return
        confirmation(plan)
        if (
            migration.check_gates(plan, progress, "provision") != disks
            or snapshot_disks(plan) != before
            or provisioner(plan) != script
        ):
            raise migration.MigrationError(
                "Target or provisioner changed during approval"
            )
        migration.verify_unmounted_targets(plan)
        verify_provision_namespace(script, disks)
        migration.verify_independent_state(state, progress, disks)
        # Publish validated durable intent before any disk change.
        record = save_journal(state, record, phase=Phase.RUNNING, before=before)
        try:
            run_provisioner(script, lock)
            if migration.probe_disks(plan) != disks:
                raise migration.MigrationError(
                    "Disk identity changed during provisioning"
                )
            identities = migration.verify_layout(plan, disks)
            save_journal(state, record, phase=Phase.COMPLETE, mounts=identities)
        except BaseException:
            save_journal(state, record, phase=Phase.INTERRUPTED)
            raise
        print("Layout provisioned and mounted. No installation or reboot performed.")


def next_step(state: Path) -> NextStep:
    with migration.locked_state(state):
        plan = migration.load_plan(state)
        migration.verify_source(plan)
        progress = migration.load_progress(state, plan)
        base = {"host": plan["spec"]["host"], "plan_id": plan["plan_id"]}
        if progress["install"]["status"] == "complete":
            return NextStep(
                **base,
                action=Action.ACCEPT,
                stage="acceptance",
                reason="Perform physical boot/application/recovery acceptance; "
                "keep recovery copies. No automatic reboot.",
                required_checks=sorted(migration.required_checks("acceptance", plan)),
            )
        if progress["install"]["status"] in {"running", "interrupted"}:
            return NextStep(
                **base,
                action=Action.INSTALL_RECOVERY,
                stage="install-recovery",
                required_checks=sorted(
                    migration.required_checks("install-recovery", plan)
                ),
                reason="Use migration install recovery; never repartition.",
            )
        record = load_journal(state, plan) if journal_path(state).exists() else None
        if record and record.phase in {Phase.RUNNING, Phase.INTERRUPTED}:
            return NextStep(
                **base,
                action=Action.RECOVER,
                reason="Uncertain provisioning. Inspect retained disk metadata. "
                "recover --apply accepts only a verified existing layout; "
                "it cannot rerun formatting.",
            )
        for stage in migration.stage_order(plan):
            if stage == "prepared":
                break
            try:
                migration.check_attestation(stage, plan, progress)
            except (ValueError, OSError) as error:
                return NextStep(
                    **base,
                    action=Action.ASSESS,
                    stage=stage,
                    reason=f"Record actual {stage} evidence: {error}",
                    required_checks=sorted(migration.required_checks(stage, plan)),
                )
        if record is None:
            return NextStep(
                **base,
                action=Action.PREPARE,
                reason="Initialize the pinned provision journal on the controller.",
            )
        if record.phase == Phase.PLANNED:
            return NextStep(
                **base,
                action=Action.PROVISION,
                reason="Boot tested installer media; retain state independently. "
                "Provision only after identity checks and typed approval.",
            )
        try:
            migration.check_attestation("prepared", plan, progress)
        except (ValueError, OSError) as error:
            return NextStep(
                **base,
                action=Action.PREPARE_ACCESS,
                stage="prepared",
                reason="Stage original or explicitly enrolled credentials and "
                "secondary keys; verify the boot password receipt. "
                f"Access preparation preserves existing credentials. {error}",
                required_checks=sorted(migration.required_checks("prepared", plan)),
            )
        return NextStep(
            **base,
            action=Action.INSTALL,
            reason="Validate the full prepared target and confirm install-only.",
        )


def advance(state: Path, *, apply: bool = False) -> NextStep:
    step = next_step(state)
    if not apply:
        return step
    match step.action:
        case Action.PREPARE:
            prepare(state)
        case Action.PROVISION:
            provision(state, apply=True)
        case Action.PREPARE_ACCESS | Action.INSTALL:
            # The delegated operation compares these identities under its own
            # machine-wide lock immediately before any mutation.
            with migration.locked_state(state):
                plan = migration.load_plan(state)
                record = load_journal(state, plan)
                if record.phase != Phase.COMPLETE:
                    raise migration.MigrationError("Provisioning is not complete")
                recorded = record.model_dump(mode="json")["mounts"]
            if step.action == Action.PREPARE_ACCESS:
                migration.prepare_access(state, expected_mounts=recorded)
            else:
                migration.install(state, expected_mounts=recorded)
        case Action.ASSESS | Action.RECOVER | Action.INSTALL_RECOVERY | Action.ACCEPT:
            raise migration.MigrationError(step.reason)
    return next_step(state)


def configured_target(config_path: Path, host: str) -> tuple[dict, Path]:
    if not migration.HOST.fullmatch(host):
        raise migration.MigrationError("Invalid inventory host name")
    config = AutoconfConfig.load(config_path)
    settings = config.boot_storage
    if host not in settings.hosts:
        raise migration.MigrationError(
            f"Add boot_storage.hosts.{host} to {config.source}"
        )
    spec = settings.hosts[host].model_dump(mode="json") | {
        "schema_version": 1,
        "host": host,
        "checkout": str(config.nix_output),
    }
    migration.validate_spec(spec)
    if settings.state_root is None:
        raise migration.MigrationError(
            "Set boot_storage.state_root in autoconf/config.yml to an existing "
            "private independent directory; "
            "no recovery location is configured"
        )
    state = settings.state_root / host
    if (state / "plan.json").exists():
        with migration.locked_state(state):
            if migration.load_plan(state)["spec"] != spec:
                raise migration.MigrationError(
                    "Autoconf differs from the saved plan; preserve its recovery state"
                )
    return spec, state


class OperatorEvidence(Contract):
    schema_version: Literal[1] = 1
    plan_id: str
    stage: str
    checks: dict[str, bool]
    artifacts: list[str] = Field(min_length=1)


def guidance() -> dict[str, str]:
    return load_unique_yaml_file(Path(__file__).with_name("boot-setup-guidance.yml"))


def show_step(
    step: NextStep, state: Path, config: Path, *, as_json: bool = False
) -> None:
    if as_json:
        print(step.model_dump_json(indent=2))
        return

    def command(action: str) -> str:
        installer = step.action in {
            Action.PROVISION,
            Action.PREPARE_ACCESS,
            Action.INSTALL,
            Action.RECOVER,
        }
        return shlex.join(
            (
                ["python", "-m", "lx_administration.storage.boot_setup"]
                if installer
                else ["devenv", "shell", "boot-storage-setup"]
            )
            + [
                action,
                "--host",
                step.host,
                "--config",
                str(config),
            ]
        )

    print(f"\nHost: {step.host} | Saved plan: {step.plan_id}\nRecovery state: {state}")
    print(f"Next step: {step.stage or step.action.value}\n{step.reason}")
    print(
        "If a check is unclear or fails, stop and ask for help. "
        "Do not guess or mark it VERIFIED."
    )
    if step.action == Action.PREPARE_ACCESS:
        print("First stage the required credentials, then prepare access:")
        print(command("advance") + " --apply")
        print("After access preparation, complete and review the checks below.")
    if step.required_checks:
        descriptions = guidance()
        print("\nThe operator must complete these checks and record the results:")
        for index, check in enumerate(step.required_checks, 1):
            print(f"{index}. {descriptions[check]}\n   Evidence check: {check}")
        report = state / f"{step.stage}-notes.txt"
        print(f"\nWrite dated results and recovery locations in {report} (mode 0600).")
        print("Do not include passwords, private keys or patient data in the notes.")
        print("When all checks actually pass, record your review with:")
        print(
            f'{command("review")} --assessor "$USER" '
            f"--report {shlex.quote(str(report))}"
        )
        print(
            "Review asks for explicit confirmation of each check; "
            "it never proves them automatically."
        )
    if step.action == Action.ASSESS:
        print(
            "Rerunning plan will not complete this review. "
            "No disk erasure is scheduled."
        )
    elif step.action in {
        Action.PREPARE,
        Action.PROVISION,
        Action.INSTALL,
    }:
        print("\nNext command (after completing the instructions above):")
        print(command("advance") + " --apply")
        if step.action == Action.PROVISION:
            print(
                "Run from tested installer media on this host. "
                "Erasure requires typed confirmation."
            )
    elif step.action == Action.RECOVER:
        print(
            "Inspect and mount the intended layout from trusted installer media. Then:"
        )
        print(command("recover") + ' --assessor "$USER" --apply')
    elif step.action == Action.INSTALL_RECOVERY:
        print(
            "After review, use the documented install --retry-interrupted procedure; "
            "never rerun Disko."
        )


def review(state: Path, assessor: str, report: Path) -> None:
    if not sys.stdin.isatty():
        raise migration.MigrationError(
            "Review requires an interactive terminal and actual completed checks"
        )
    step = next_step(state)
    if step.stage is None or not step.required_checks:
        raise migration.MigrationError("No human assessment is currently requested")
    migration.private_path(report)
    if not report.read_text().strip():
        raise migration.MigrationError(
            "Write the actual test results in the report first"
        )
    report_hash = migration.file_digest(report)
    descriptions = guidance()
    for check in step.required_checks:
        print(descriptions[check])
        if (
            input("Type VERIFIED only if you performed/reviewed this successfully: ")
            != "VERIFIED"
        ):
            raise migration.MigrationError(
                "Review cancelled; no assessment was recorded"
            )
    if next_step(state) != step or migration.file_digest(report) != report_hash:
        raise migration.MigrationError(
            "Plan, requested checks or report changed during review"
        )
    evidence = state / f"{step.stage}-review-{uuid4().hex}.json"
    payload = OperatorEvidence(
        plan_id=step.plan_id,
        stage=step.stage,
        checks=dict.fromkeys(step.required_checks, True),
        artifacts=[str(report)],
    )
    atomic_create_file(
        destination=evidence,
        content=[payload.model_dump_json().encode()],
        file_mode=0o600,
    )
    print(
        json.dumps({"event": "operator_review_created", "path": str(evidence)}),
        file=sys.stderr,
    )
    migration.attest(state, step.stage, evidence, assessor)
    print(
        "Operator assessment recorded. This is human evidence, "
        "not an automated recovery test."
    )


def current_host(config_path: Path) -> str:
    hosts = AutoconfConfig.load(config_path).boot_storage.hosts
    hostname = socket.gethostname().split(".", 1)[0]
    if hostname in hosts:
        return hostname
    # Live installers often have a generic hostname; match recorded hardware.
    try:
        hardware = migration.DMI_UUID.read_text().strip().lower()
    except PermissionError as error:
        raise migration.MigrationError(
            f"No boot setup entry for {hostname}; hardware identification requires "
            "read access to the DMI UUID. Select --host explicitly if needed."
        ) from error
    matches = [
        host
        for host, settings in hosts.items()
        if settings.hardware_uuid.lower() == hardware
    ]
    if len(matches) != 1:
        raise migration.MigrationError(
            "Current hardware must match exactly one Autoconf boot_storage host"
        )
    return matches[0]


def run_workflow(
    spec: dict, state: Path, config: Path, *, apply: bool, device: str | None = None
) -> None:
    from lx_administration.storage import recovery_media

    if apply and not sys.stdin.isatty():
        raise migration.MigrationError("Apply requires a private interactive terminal")
    show_target(spec)
    if not apply:
        if (state / "plan.json").exists():
            show_step(next_step(state), state, config)
        else:
            recovery_media.setup(spec, state, apply=False, device=device)
        print(
            "Preview only. Set LUXNIX_BOOT_SETUP_APPLY=1 to run the task interactively."
        )
        return
    recovery_media.setup(spec, state, apply=True, device=device)
    migration.plan_spec(spec, state)
    prepare(state)
    visited = set()
    while True:
        step = next_step(state)
        show_step(step, state, config)
        marker = (step.action, step.stage)
        if marker in visited:
            raise migration.MigrationError(
                "Workflow did not advance; inspect the saved state"
            )
        visited.add(marker)
        if step.action in {Action.RECOVER, Action.INSTALL_RECOVERY}:
            print(
                "Paused: inspect the interrupted operation and use "
                "the explicit recovery command."
            )
            return
        if step.action in {Action.PROVISION, Action.INSTALL, Action.PREPARE_ACCESS}:
            if os.geteuid() != 0 or migration.mount_record("/")["fstype"] not in {
                "tmpfs",
                "overlay",
                "squashfs",
            }:
                print(
                    "Paused: boot installer media and mount recovery at /recovery. "
                    "Run the reviewed workflow as root there. "
                    "Do not run sudo devenv on the installed system."
                )
                return
            advance(state, apply=True)
            if step.action == Action.INSTALL:
                print(
                    "Paused: perform physical cold-boot and application acceptance, "
                    "then rerun this task. No automatic reboot."
                )
                return
            if step.action == Action.PROVISION:
                continue
        elif step.action == Action.PREPARE:
            prepare(state)
            continue
        if step.action in {Action.ASSESS, Action.PREPARE_ACCESS, Action.ACCEPT}:
            if step.action == Action.ACCEPT:
                with migration.locked_state(state):
                    plan = migration.load_plan(state)
                    progress = migration.load_progress(state, plan)
                    try:
                        migration.check_attestation(
                            "acceptance", plan, progress, fresh=False
                        )
                    except (ValueError, OSError):
                        pass  # Show the required human review below; never approve it.
                    else:
                        print(
                            "Complete: physical acceptance is recorded. "
                            "Retain recovery copies."
                        )
                        return
            report = state / f"{step.stage}-notes.txt"
            if not report.is_file():
                print(
                    f"Paused: write the completed check results to {report}, "
                    "then rerun the same task. No assessment has been approved."
                )
                return
            assessor = input(
                "Name of the operator who performed/reviewed these checks: "
            ).strip()
            if not assessor:
                raise migration.MigrationError(
                    "An operator name is required; no review recorded"
                )
            review(state, assessor, report)
            if step.action == Action.ACCEPT:
                print("Complete: acceptance review recorded. Retain recovery copies.")
                return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    observation = sub.add_parser(
        "observe", help="Read target identities as reviewable YAML"
    )
    observation.add_argument("--checkout", required=True, type=Path)
    observation.add_argument("--host", required=True)
    observation.add_argument(
        "--hardware-uuid", help="UUID read on the target; rechecked before provisioning"
    )
    observation.add_argument(
        "--installation", required=True, choices=["migration", "fresh", "disposable"]
    )
    observation.add_argument(
        "--source-retention",
        required=True,
        choices=["old-disks", "whole-disk-image", "new-disks", "discard-approved"],
    )
    for action in (
        "plan",
        "next",
        "advance",
        "recover",
        "attest",
        "status",
        "setup-media",
        "review",
        "run",
    ):
        command = sub.add_parser(action)
        host_selection = command.add_mutually_exclusive_group(required=True)
        host_selection.add_argument("--host")
        host_selection.add_argument("--current-host", action="store_true")
        command.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
        command.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable next-step output",
        )
        if action in {"advance", "recover", "setup-media", "run"}:
            command.add_argument("--apply", action="store_true")
        if action in {"setup-media", "run"}:
            command.add_argument(
                "--device", help="Select one detected external filesystem"
            )
        if action in {"recover", "attest", "review"}:
            command.add_argument("--assessor", required=True)
        if action == "review":
            command.add_argument("--report", type=Path, required=True)
        if action == "attest":
            command.add_argument("--stage", choices=migration.STAGES, required=True)
            command.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.action != "observe":
            host = current_host(args.config) if args.current_host else args.host
            spec, state = configured_target(args.config, host)
            if args.action not in {"run", "status"} and not args.json:
                show_target(spec)
        match args.action:
            case "observe":
                print(
                    yaml.safe_dump(
                        observe(
                            args.checkout,
                            args.host,
                            args.installation,
                            args.source_retention,
                            hardware_uuid=args.hardware_uuid,
                        ),
                        sort_keys=False,
                    ),
                    end="",
                )
                return
            case "run":
                run_workflow(
                    spec, state, args.config, apply=args.apply, device=args.device
                )
                return
            case "setup-media":
                from lx_administration.storage import recovery_media

                recovery_media.setup(spec, state, apply=args.apply, device=args.device)
                if not args.apply:
                    return
                migration.plan_spec(spec, state)
                prepare(state)
            case "plan":
                migration.plan_spec(spec, state)
                prepare(state)
            case "review":
                review(state, args.assessor, args.report)
            case "attest":
                migration.attest(state, args.stage, args.evidence, args.assessor)
            case "status":
                print(json.dumps(migration.status(state), indent=2))
                return
            case "next":
                pass
            case "advance":
                show_step(
                    advance(state, apply=args.apply),
                    state,
                    args.config,
                    as_json=args.json,
                )
                return
            case "recover":
                provision(state, apply=args.apply, recover_by=args.assessor)
        show_step(next_step(state), state, args.config, as_json=args.json)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        parser.exit(
            1,
            f"Root setup stopped: {error}\n"
            "Keep the plan, journal and recovery copies.\n",
        )


if __name__ == "__main__":
    main()
