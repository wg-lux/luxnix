"""Classify root storage and select a matching root layout from recovery media.

Never formats, encrypts or changes LUKS keyslots. `restore` writes only the system
profile and boot entries of an already mounted target, and only with --apply.
Standard library only, so the recovery image needs no application packages.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

if __package__:
    from . import root_guard
else:
    import root_guard

PLAINTEXT, ENCRYPTING, ENCRYPTED, UNKNOWN = (
    root_guard.PLAINTEXT, root_guard.ENCRYPTING,
    root_guard.ENCRYPTED, root_guard.UNKNOWN,
)

PROCEDURES = {
    PLAINTEXT: [
        "Root is plaintext: generations that mount /dev/mapper/cryptroot cannot boot.",
        "Mount it: mount -o subvol=root <partition> /mnt, and its nix, home, persist "
        "and log subvolumes plus the EFI partition below /mnt.",
        "List choices: luxnix-boot-recover generations --root /mnt",
        "Preview: luxnix-boot-recover restore --root /mnt --generation <plaintext-N>",
        "Select it by adding --apply, then reboot.",
    ],
    ENCRYPTING: [
        "Encryption stopped part-way: no installed generation can boot this disk yet.",
        "Do not format the partition and do not run a filesystem repair on it.",
        "Boot the staged LuxNix migration entry; the boot default already points "
        "there. Mount the recovery drive at /recovery and run: luxnix-migration run "
        "--apply. It resumes from the LUKS2 header.",
    ],
    ENCRYPTED: [
        "Root is encrypted: plaintext-root generations cannot boot, so choose only "
        "generations that mount /dev/mapper/cryptroot.",
        "Unlock: cryptsetup open --type luks2 <partition> cryptroot",
        "Mount /dev/mapper/cryptroot subvolumes and the EFI partition below /mnt.",
        "List choices: luxnix-boot-recover generations --root /mnt",
        "Preview: luxnix-boot-recover restore --root /mnt --generation <encrypted-N>",
        "Select it by adding --apply, then reboot.",
    ],
    UNKNOWN: [
        "The partition has no recognized signature. Stop: do not format or repair it.",
        "Compare it against the disk identity in the migration plan and restore the "
        "LUKS2 header backup only if the plan names this exact partition.",
    ],
}


classify = root_guard.classify_root


def probe(partition: str) -> str:
    signature = root_guard.run(
        "blkid", "--probe", "--output", "value", "--match-tag", "TYPE", partition
    )
    return classify(
        signature,
        root_guard.probe_luks(partition) if signature == "crypto_LUKS" else None,
    )


def compatible(state: str, generation: dict) -> bool:
    return generation["root"] == state and state in {PLAINTEXT, ENCRYPTED}


def choose(state: str, generations: list[dict], number: int) -> dict:
    selected = next((g for g in generations if g["number"] == number), None)
    if selected is None:
        raise ValueError(f"Generation {number} is not retained on this target")
    if not compatible(state, selected):
        consequence = (
            "compatibility cannot be established"
            if state == UNKNOWN or selected["root"] is None else "it would not boot"
        )
        raise ValueError(
            f"Generation {number} mounts {selected['root'] or 'an unknown'} root but "
            f"this disk is {state}; {consequence}"
        )
    return selected


mounted_root_state = root_guard.mounted_root_state

def restore(root: Path, number: int, *, apply: bool) -> None:
    state = mounted_root_state(root)
    selected = choose(state, root_guard.probe_generations(root), number)
    profile = "/nix/var/nix/profiles/system"
    commands = [
        ["nix-env", "--profile", profile, "--set", selected["system"]],
        [f"{selected['system']}/bin/switch-to-configuration", "boot"],
    ]
    print(
        f"Target root is {state}; generation {number}'s declared root layout matches."
    )
    print("This comparison does not prove that the generation will boot.")
    print("This changes the system profile and boot entries; no disk data is touched.")
    if not apply:
        print("Preview only. Add --apply to select this generation.")
        return
    for command in commands:
        subprocess.run(
            ["nixos-enter", "--root", str(root), "--", *command],
            check=True,
            env={"NIXOS_INSTALL_BOOTLOADER": "1", "PATH": "/run/current-system/sw/bin"},
        )
    print(f"Generation {number} is now the boot default. Reboot when ready.")


def guide(partition: str | None) -> None:
    if partition is None:
        print("Show the procedure for one state; run on recovery media or the host:")
        print("  luxnix-boot-recover classify --partition <root-partition>")
        print("Changes nothing and is safe to repeat.")
        return
    state = probe(partition)
    print(f"{partition}: {state}")
    for step, text in enumerate(PROCEDURES[state], 1):
        print(f"  {step}. {text}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["classify", "generations", "restore"])
    parser.add_argument("--partition")
    parser.add_argument("--root", type=Path, default=Path("/mnt"))
    parser.add_argument("--generation", type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        match args.command:
            case "classify":
                guide(args.partition)
            case "generations":
                print(json.dumps(root_guard.probe_generations(args.root), indent=2))
            case "restore":
                if args.generation is None:
                    raise ValueError("--generation is required")
                restore(args.root, args.generation, apply=args.apply)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"Recovery stopped; nothing further was changed: {error}")


if __name__ == "__main__":
    main()
