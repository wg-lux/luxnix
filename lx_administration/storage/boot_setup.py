"""Sequential root setup: preview by default, confirmed provisioning, no auto-retry."""

from __future__ import annotations

import argparse
from enum import StrEnum
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml

from lx_administration.storage import boot_migration as migration
from lx_administration.utils.file_operations import atomic_write_file


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


def observe(checkout: Path, host: str, installation: str, retention: str) -> dict:
    """Collect a specification on the target; never select substitute disks."""
    if not migration.HOST.fullmatch(host):
        raise migration.MigrationError("Invalid inventory host name")
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
        "hardware_uuid": migration.DMI_UUID.read_text().strip(),
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
        for disk in plan["spec"]["disks"]:
            terminal.write(
                f"{disk['path']} serial={disk['serial']} "
                f"size_bytes={disk['size_bytes']}\n"
            )
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
                reason="Perform physical boot/application/recovery acceptance; "
                "keep recovery copies. No automatic reboot.",
                required_checks=sorted(migration.required_checks("acceptance", plan)),
            )
        if progress["install"]["status"] in {"running", "interrupted"}:
            return NextStep(
                **base,
                action=Action.INSTALL_RECOVERY,
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    observation = sub.add_parser(
        "observe", help="Read target identities as reviewable YAML"
    )
    observation.add_argument("--checkout", required=True, type=Path)
    observation.add_argument("--host", required=True)
    observation.add_argument(
        "--installation", required=True, choices=["migration", "fresh", "disposable"]
    )
    observation.add_argument(
        "--source-retention",
        required=True,
        choices=["old-disks", "whole-disk-image", "new-disks", "discard-approved"],
    )
    for action in ("plan", "next", "advance", "recover"):
        command = sub.add_parser(action)
        command.add_argument("--state", required=True, type=Path)
        if action == "plan":
            command.add_argument("--spec", required=True, type=Path)
        if action in {"advance", "recover"}:
            command.add_argument("--apply", action="store_true")
        if action == "recover":
            command.add_argument("--assessor", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        match args.action:
            case "observe":
                print(
                    yaml.safe_dump(
                        observe(
                            args.checkout,
                            args.host,
                            args.installation,
                            args.source_retention,
                        ),
                        sort_keys=False,
                    ),
                    end="",
                )
                return
            case "plan":
                migration.create_plan(args.spec, args.state)
                prepare(args.state)
            case "next":
                pass
            case "advance":
                print(advance(args.state, apply=args.apply).model_dump_json(indent=2))
                return
            case "recover":
                provision(args.state, apply=args.apply, recover_by=args.assessor)
        print(next_step(args.state).model_dump_json(indent=2))
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        parser.exit(
            1,
            f"Root setup stopped: {error}\n"
            "Keep the plan, journal and recovery copies.\n",
        )


if __name__ == "__main__":
    main()
