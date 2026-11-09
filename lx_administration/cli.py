"""Encrypted installation by default; preservation is an explicit operation."""

from __future__ import annotations

import sys

USAGE = """\
Usage: luxnix [--profile <file.yml>] | <command> [options]

  prepare            Save the migration plan (changes no disk; safe to repeat)
  status             Show migration stage and evidence (read-only; safe to repeat)
  inspect            Verify existing encrypted storage (HOST)
  install            Prepare a fresh encrypted installer (default; --profile <file.yml>)
  migrate            Encrypt root in place, step by step (resumes; safe to rerun)
  verify             Check the real disk against the plan (read-only; safe to repeat)
  recover            Show the recovery procedure for this disk (--partition <path>);
                     with --assessor, accept the layout after interrupted encryption
  retire-containers  Remove the old containers after acceptance (--apply deletes)
  storage <action>   Any boot-storage-setup action, for administrators

Inside the devenv shell run `luxnix ...`; from outside, `devenv shell luxnix ...`.
"""

# What each command changes, shown before it runs.
EFFECTS = {
    "prepare": "Writes the plan to recovery media; no disk changes. Safe to repeat.",
    "status": "Reads saved migration state only; no changes. Safe to repeat.",
    "migrate": "Guides each step and asks before any disk change. Safe to rerun; it resumes.",
    "verify": "Reads the disk against the saved plan; no changes. Safe to repeat.",
    "recover": "Read-only without --assessor; with --assessor --apply it accepts the existing layout and never formats.",
}

# Each operator command is one existing boot-storage-setup action.
COMMANDS = {
    "prepare": ["plan"],
    "status": ["status"],
    "migrate": ["guide"],
    "verify": ["verify"],
    "recover": ["recover"],
    "retire-containers": ["retire-containers"],
    "storage": [],
}


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    command, *rest = argv or ["install"]
    if command in {"-h", "--help", "help"}:
        print(USAGE, end="")
        return
    if command.startswith("-"):
        command, rest = "install", argv
    if command in {"install", "inspect"}:
        from lx_administration.storage import fresh_install

        fresh_install.main(["--inspect", *rest] if command == "inspect" else rest)
        return
    if command not in COMMANDS:
        sys.exit(f"Unknown command: {command}\n\n{USAGE}")
    if command in EFFECTS:
        print(EFFECTS[command], file=sys.stderr)
    if command == "recover" and "--assessor" not in rest:
        from lx_administration.storage import root_recovery

        root_recovery.main(["classify", *rest])
        return
    from lx_administration.storage import boot_setup

    boot_setup.main([*COMMANDS[command], *rest])


if __name__ == "__main__":
    main()
