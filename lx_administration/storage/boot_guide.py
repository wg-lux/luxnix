"""One resumable command for root encryption on the current host.

It does whatever can be measured and asks only about what cannot, such as a physical
boot test. It never answers for the operator: every check still needs a typed VERIFIED,
and nothing here starts the encryption.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

from lx_administration.storage import boot_migration as migration
from lx_administration.storage import boot_setup as setup
from lx_administration.storage import (
    recovery_custody,
    recovery_media,
    secret_preflight,
)
from lx_administration.storage.boot_migration import Stopped
from lx_administration.utils.file_operations import atomic_write_file

CUSTODY_FILE = Path("/recovery/luxnix-custody.luks")
CUSTODY_MAPPING = "luxnix-custody"
CUSTODY_MOUNT = Path("/run/luxnix-custody")
CUSTODY_DIRECTORY = CUSTODY_MOUNT / "custody"
CUSTODY_SIZE = "2G"
ANSWERS = "recovery-checks.json"
GUIDED_NOTES = "recovery-notes-guided.txt"
ANSWER_LIFETIME = 24 * 3600
# Measured checks first, so a reboot for the physical tests comes last.
CHECK_ORDER = (
    "in_place_backup_acknowledged",
    "plaintext_remnants_reviewed",
    "independent_credentials_tested",
    "vault_recovery_tested",
    "console_boot_tested",
    "trusted_installer_tested",
)
PATIENT_DATA_PATTERNS = (
    "*.mp4", "*.avi", "*.mov", "*.mkv", "*.dcm", "*.dicom", "*.nii", "*.nii.gz",
    "*.sql", "*.sql.gz", "*.dump", "*.pdf",
)  # fmt: skip
SCAN_ROOTS = ("/", "/home", "/persist", "/var/log", "/tmp", "/var/tmp")


def interactive(*command: str) -> None:
    """Run with the real terminal, so cryptsetup can ask for its passphrase."""
    result = subprocess.run([*secret_preflight.root_prefix(), *command], check=False)
    if result.returncode:
        raise migration.MigrationError(
            f"{Path(command[0]).name} failed (exit {result.returncode}); "
            "nothing was deleted"
        )


def quiet(*command: str) -> bool:
    return secret_preflight.privileged(*command).returncode == 0


def custody_mounted() -> bool:
    return quiet("mountpoint", "-q", str(CUSTODY_MOUNT))


def mount_custody() -> None:
    interactive("mkdir", "-p", str(CUSTODY_MOUNT))
    interactive(
        "mount", "-o", "nosuid,nodev,noexec", f"/dev/mapper/{CUSTODY_MAPPING}",
        str(CUSTODY_MOUNT),
    )  # fmt: skip


def open_custody() -> None:
    if not Path("/dev/mapper", CUSTODY_MAPPING).exists():
        print(f"Enter the custody passphrase for {CUSTODY_FILE}.")
        interactive("cryptsetup", "open", str(CUSTODY_FILE), CUSTODY_MAPPING)
    mount_custody()


def close_custody() -> None:
    interactive("umount", str(CUSTODY_MOUNT))
    interactive("cryptsetup", "close", CUSTODY_MAPPING)


def create_custody() -> None:
    # luksFormat on an open file destroys it silently, so only a new file is formatted.
    if secret_preflight.exists(CUSTODY_FILE):
        raise migration.MigrationError(f"{CUSTODY_FILE} exists; refusing to format it")
    print(
        f"\nSecrets need encrypted custody outside this disk. This creates a new "
        f"{CUSTODY_SIZE} encrypted file, {CUSTODY_FILE}. Keep its passphrase outside "
        "this computer: losing it loses everything in custody."
    )
    if input("Type CREATE CUSTODY to continue: ") != "CREATE CUSTODY":
        raise Stopped("Custody was not created.")
    interactive("truncate", "-s", CUSTODY_SIZE, str(CUSTODY_FILE))
    interactive(
        "cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode",
        "--verify-passphrase", str(CUSTODY_FILE),
    )  # fmt: skip
    interactive("cryptsetup", "open", str(CUSTODY_FILE), CUSTODY_MAPPING)
    interactive("mkfs.ext4", "-q", f"/dev/mapper/{CUSTODY_MAPPING}")
    mount_custody()
    setup.success(f"Custody created at {CUSTODY_DIRECTORY}.")


def ensure_custody() -> Path:
    """Reuse, reopen or create the default custody; never format an existing file."""
    if not custody_mounted():
        if not secret_preflight.exists(CUSTODY_FILE):
            create_custody()
        elif quiet("cryptsetup", "isLuks", str(CUSTODY_FILE)):
            open_custody()
        else:
            raise migration.MigrationError(
                f"{CUSTODY_FILE} is not a LUKS file; move it aside and rerun"
            )
    if not secret_preflight.is_directory(CUSTODY_DIRECTORY):
        user, group = str(os.getuid()), str(os.getgid())
        interactive(
            "install", "-d", "-m", "0700", "-o", user, "-g", group,
            str(CUSTODY_DIRECTORY),
        )  # fmt: skip
    return CUSTODY_DIRECTORY


def fill_custody(state: Path, custody: Path, *, reopenable: bool) -> None:
    """Copy what is missing, then prove the copies survive closing the volume."""
    missing = secret_preflight.missing_copies(state, custody)
    if not missing:
        return
    print(f"\nThese {len(missing)} secrets are not in custody yet:")
    for live, _ in missing:
        print(f"  {live}")
    print(f"Copying them to {custody}; the originals are not changed.")
    for live, copy in missing:
        secret_preflight.copy_to_custody(live, copy)
    setup.success(f"Copied {len(missing)} secrets into custody.")
    if reopenable:
        print("\nClosing and reopening custody to prove the copies were stored.")
        close_custody()
        open_custody()


def scan_for_patient_data() -> tuple[int, list[str]]:
    """Count likely patient files outside the containers; never list their names."""
    names: list[str] = []
    for pattern in PATIENT_DATA_PATTERNS:
        names += ["-o", "-iname", pattern]
    # find does not dedupe start points, so keep one root per filesystem.
    present = (r for r in reversed(SCAN_ROOTS) if Path(r).exists())
    roots = list({os.stat(r).st_dev: r for r in present}.values())
    result = secret_preflight.privileged(
        "find", *roots, "-xdev", "-type", "f", "(", *names[1:], ")", "-printf", "%h\n"
    )
    folders = Counter(
        "/".join(line.split("/")[:4]) or "/"
        for line in result.stdout.decode(errors="replace").splitlines()
    )
    lines = [f"{count:7} {folder}" for folder, count in folders.most_common(20)]
    return sum(folders.values()), lines


def measure_size(path: Path) -> str:
    try:
        output = secret_preflight.privileged("du", "-sh", str(path)).stdout
    except subprocess.SubprocessError:
        return "not measured (it took too long)"
    return output.decode(errors="replace").split("\t")[0].strip() or "not measured"


def root_used() -> str:
    result = subprocess.run(
        ["df", "-h", "--output=used", "/"], capture_output=True, text=True, check=False
    )
    return result.stdout.split()[-1] if result.stdout.split() else "not measured"


def ask_backup(spec: dict) -> str:
    location = input(
        "Absolute path of the mounted backup, or Enter if you are going without one: "
    ).strip()
    if not location:
        name = input("Going without a backup. Who accepts this risk? (name) ").strip()
        if not name:
            raise Stopped(
                "A tested backup or a named person accepting the risk is needed."
            )
        return f"No backup. Risk accepted by: {name}"
    path = Path(location)
    if not path.is_absolute() or not secret_preflight.exists(path):
        raise migration.MigrationError(f"{location} is not an existing absolute path")
    selected = {os.path.realpath(d["path"]) for d in spec["disks"]}
    if recovery_custody.storage_disks(path.resolve()) & selected:
        raise migration.MigrationError(
            f"{location} is on the disk being encrypted, so it is not a backup"
        )
    print("Measuring the backup...")
    size = measure_size(path)
    print(f"Backup size: {size} | Space used on root: {root_used()}")
    print("The backup is on a different disk. Only you can prove it restores.")
    tested = input("How did you test restoring it? (no secrets) ").strip()
    if not tested:
        raise Stopped("A backup counts only once a restore has been tested.")
    return f"Backup at {location}, size {size}. Restore test: {tested}"


def measured_detail(check: str, spec: dict, state: Path) -> str:
    """Print and return what the machine can establish for one check."""
    if check == "in_place_backup_acknowledged":
        return ask_backup(spec)
    if check == "plaintext_remnants_reviewed":
        print("Searching the unencrypted root for likely patient files...")
        total, folders = scan_for_patient_data()
        print(f"Found {total} video, DICOM, database dump or PDF files, by folder:")
        print("\n".join(folders) or "  none")
        print(
            "This search goes by file type and cannot prove absence: it misses other "
            "formats, deleted files and paths hidden under mounts."
        )
        return f"File-type search of unencrypted root found {total} candidate files."
    if check in {"independent_credentials_tested", "vault_recovery_tested"}:
        receipt = json.loads((state / migration.PREFLIGHT_RECEIPT).read_text())
        verified = sum(i["status"] == "verified" for i in receipt["items"])
        detail = (
            f"Preflight verified {verified} of {len(receipt['items'])} required "
            f"secrets in {receipt['custody']}, outside the selected disks, and the "
            "admin password against its saved hash."
        )
        items = receipt["items"]
        fresh = [i["path"] for i in items if i["status"] == "salt-regenerated"]
        if fresh:
            detail += f" New salts will be created for: {', '.join(fresh)}."
        print(detail)
        if check == "independent_credentials_tested":
            print("Yours to confirm: the custody passphrase is off this computer.")
        return detail
    return ""


PHYSICAL_INSTRUCTIONS = {
    "console_boot_tested": "Do this at the machine with a keyboard and screen.",
    "trusted_installer_tested": (
        "Reboot into the installer, check it sees both drives, boot back into this "
        "system, then rerun this same command. It remembers your answers."
    ),
}


def load_answers(state: Path, plan_id: str) -> dict:
    path = state / ANSWERS
    if not path.exists():
        return {}
    saved = json.loads(path.read_text())
    if saved.get("plan_id") != plan_id:
        return {}
    # An old answer would not satisfy the 24-hour review limit anyway.
    return {
        check: answer
        for check, answer in saved["checks"].items()
        if time.time() - answer["confirmed_at"] < ANSWER_LIFETIME
    }


def ask_checks(spec: dict, state: Path, step: setup.NextStep) -> dict:
    answers = load_answers(state, step.plan_id)
    descriptions = setup.guidance()
    remaining = sorted(
        (c for c in step.required_checks if c not in answers),
        key=lambda c: CHECK_ORDER.index(c) if c in CHECK_ORDER else len(CHECK_ORDER),
    )
    for number, check in enumerate(remaining, 1):
        print(f"\n--- Check {number} of {len(remaining)}: {check} ---")
        print(descriptions[check])
        detail = measured_detail(check, spec, state)
        if check in PHYSICAL_INSTRUCTIONS:
            print(PHYSICAL_INSTRUCTIONS[check])
        answer = input("Type VERIFIED only if you did this, or press Enter to stop: ")
        if answer != "VERIFIED":
            raise Stopped("Your earlier answers are saved.")
        answers[check] = {"confirmed_at": time.time(), "detail": detail}
        migration.atomic_json(
            state / ANSWERS, {"plan_id": step.plan_id, "checks": answers}
        )
    return answers


def write_notes(state: Path, answers: dict) -> Path:
    notes = state / GUIDED_NOTES
    lines = []
    for check, answer in sorted(answers.items()):
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(answer["confirmed_at"]))
        lines.append(f"{when} {check}: confirmed. {answer['detail']}".rstrip())
    atomic_write_file(
        destination=notes,
        content=[("\n".join(lines) + "\n").encode()],
        file_mode=0o600,
    )
    return notes


def recovery_stage(spec: dict, state: Path, custody: Path | None) -> None:
    reopenable = custody is None
    directory = custody or ensure_custody()
    if not setup.preflight_passed(state):
        for path in secret_preflight.restore_lost_salts(state, directory):
            print(f"Restored {path} from custody.")
        fill_custody(state, directory, reopenable=reopenable)
        secret_preflight.run(state, directory)
    step = setup.next_step(state)
    answers = ask_checks(spec, state, step)
    assessor = os.environ.get("USER") or input("Name of the operator: ").strip()
    setup.record_review(state, step, assessor, write_notes(state, answers))


def plan_is_stale(state: Path, spec: dict) -> bool:
    if not (state / "plan.json").exists():
        return False
    with migration.locked_state(state):
        plan = migration.load_plan(state)
        return plan["spec"] != spec or (
            migration.source_identity(Path(spec["checkout"])) != plan["source"]
        )


def plan_has_started(state: Path) -> bool:
    with migration.locked_state(state):
        plan = migration.load_plan(state)
        if migration.load_progress(state, plan)["install"]["status"] != "pending":
            return True
    # Outside the lock: encryption_started takes the same non-reentrant lock.
    return setup.encryption_started(state)


def replace_stale_plan(state: Path, spec: dict) -> None:
    if not plan_is_stale(state, spec):
        return
    if plan_has_started(state):
        raise migration.MigrationError(
            "The checkout or Autoconf changed, but this plan has started. Restore the "
            "planned revision to continue it; the plan cannot be replaced now"
        )
    print("\nThe checkout changed before this plan started, so it is being replaced.")
    kept = state.with_name(f"{state.name}.superseded-{uuid4().hex[:8]}")
    if not quiet("mv", "-n", str(state), str(kept)):
        raise migration.MigrationError(f"Could not move {state} aside; nothing changed")
    print(f"Old plan kept at {kept}")


def run(
    host: str, config: Path, *, device: str | None = None, custody: Path | None = None
) -> None:
    if not sys.stdin.isatty():
        raise migration.MigrationError("Use a private interactive terminal")
    spec, state = setup.target_spec(config, host)
    setup.show_target(spec)
    recovery_media.setup(spec, state, apply=True, device=device)
    replace_stale_plan(state, spec)
    if not (state / "plan.json").exists():
        setup.save_plan(spec, state)
    step = setup.next_step(state)
    if step.action == setup.Action.ASSESS and step.stage == "recovery":
        recovery_stage(spec, state, custody)
    setup.drive(state, config)
