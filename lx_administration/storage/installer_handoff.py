"""Run a saved plan's own source inside the LuxNix RAM migration environment.

The image carries only this launcher. Planning on the installed host copies the
plan's exact checkout beside its state on the recovery drive; this module checks
that copy against the plan's revision and flake.lock and runs the setup workflow
from it, so the code that converts the disk is the code that made the plan.
Afterwards it returns files created as root to the operator who owns the state,
so the installed host can continue the same plan as that operator.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys

from lx_administration.storage import boot_migration as migration
from lx_administration.storage import recovery_media

SPEC = Path("/etc/luxnix/migration.json")
SESSION = "luxnix-migration"
HOLD_WINDOW = (
    '"$@"; status=$?; printf "\\nluxnix-migration ended with exit status %s. '
    'Press Enter to close this window.\\n" "$status"; read -r _'
)


def image_host() -> str:
    host = json.loads(SPEC.read_text())["host"]
    if not isinstance(host, str) or not migration.HOST.fullmatch(host):
        raise migration.MigrationError("The migration image names no valid host")
    return host


def mount_recovery() -> None:
    """Mount the recovery drive this image was built for, unless it already is.

    The image names the filesystem by UUID. An encrypted recovery drive needs its
    own passphrase and stays an operator step.
    """
    mount = recovery_media.MOUNT
    if os.path.ismount(mount):
        return
    recovery = json.loads(SPEC.read_text())["recovery"]
    device = Path("/dev/disk/by-uuid") / str(recovery["uuid"])
    if recovery["luks_uuid"] is not None:
        raise migration.MigrationError(
            "The recovery drive is encrypted and not mounted",
            fix=f"unlock it, mount it at {mount}, then run luxnix-migration again",
        )
    if not device.exists():
        raise migration.MigrationError(
            f"The recovery drive (filesystem {recovery['uuid']}) is not connected",
            fix="connect the drive that holds this plan, then run luxnix-migration "
            "again",
        )
    mount.mkdir(mode=0o700, exist_ok=True)
    if any(mount.iterdir()):
        raise migration.MigrationError(f"Refusing to hide existing files under {mount}")
    subprocess.run(
        ["mount", "-t", recovery["fstype"], "-o", "nosuid,nodev", "--", device, mount],
        check=True,
        stdin=subprocess.DEVNULL,
    )
    print(f"Mounted the recovery drive at {mount}.", file=sys.stderr)


def plan_source(state: Path) -> Path:
    """The verified copy of the plan's source; refuses any other revision."""
    with migration.locked_state(state):
        plan = migration.load_plan(state)
    source = migration.source_copy(state, plan)
    if not source.is_dir():
        raise migration.MigrationError(
            f"The plan's source is not on the recovery drive: {source}",
            fix="on the installed host run devenv shell luxnix migrate, which "
            "saves it, then boot this environment again",
        )
    migration.private_path(source, directory=True)
    if migration.source_identity(source) != plan["source"]:
        raise migration.MigrationError(
            f"{source} does not match the plan's revision and flake.lock; "
            "move it aside for review"
        )
    return source


def hand_back(root: Path) -> list[Path]:
    """Give root-created state back to the owner of the state root.

    Only regular files and directories on the same filesystem, never links.
    """
    info = root.lstat()
    if os.geteuid() != 0 or info.st_uid == 0:
        return []
    changed = []
    for directory, subdirectories, files in os.walk(root):
        for name in [*subdirectories, *files]:
            path = Path(directory) / name
            entry = path.lstat()
            if entry.st_dev != info.st_dev:
                if name in subdirectories:
                    subdirectories.remove(name)
                continue
            if entry.st_uid == 0 and (
                stat.S_ISREG(entry.st_mode) or stat.S_ISDIR(entry.st_mode)
            ):
                os.lchown(path, info.st_uid, info.st_gid)
                changed.append(path)
    return changed


def detach_from_ssh(argv: list[str]) -> None:
    """Over SSH, run inside tmux so a dropped connection cannot stop a conversion.

    Running the same command again after a disconnect reattaches to the session.
    """
    if not os.environ.get("SSH_CONNECTION") or os.environ.get("TMUX"):
        return
    print(
        f"Continuing in tmux session {SESSION}. If the connection drops, the work "
        "continues; reconnect and run the same command to return to it.",
        file=sys.stderr,
    )
    os.execvp(
        "tmux",
        [
            "tmux",
            "new-session",
            "-A",
            "-s",
            SESSION,
            "-e",
            f"PYTHONPATH={os.environ.get('PYTHONPATH', '')}",
            # Keep the window open afterwards, so results and errors stay readable.
            "sh",
            "-c",
            HOLD_WINDOW,
            "sh",
            sys.executable,
            "-m",
            "lx_administration.storage.installer_handoff",
            *argv,
        ],
    )


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if not migration.installer_environment():
            raise migration.MigrationError(
                "luxnix-migration runs only as root inside the LuxNix RAM "
                "migration environment"
            )
        host = image_host()
        mount_recovery()
        state = recovery_media.STATE_ROOT / host
        source = plan_source(state)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        sys.exit(migration.explain_stop(error))
    detach_from_ssh(argv)
    print(f"Running this plan's own source: {source}", file=sys.stderr)
    command = [sys.executable, "-m", "lx_administration.storage.boot_setup", *argv]
    if argv and "--host" not in argv and "--current-host" not in argv:
        command += ["--host", host]
    # The terminal's Ctrl-C reaches the workflow; this launcher still hands back.
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        result = subprocess.run(
            command, env=os.environ | {"PYTHONPATH": str(source)}, check=False
        )
    finally:
        signal.signal(signal.SIGINT, previous)
        changed = hand_back(recovery_media.STATE_ROOT)
        if changed:
            print(
                f"Returned {len(changed)} new state files to the plan's operator.",
                file=sys.stderr,
            )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
