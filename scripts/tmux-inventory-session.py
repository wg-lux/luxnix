#!/usr/bin/env python3
"""Create a Tmux session from a host group in the Ansible inventory."""

from __future__ import annotations

import argparse
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lx_administration.yaml import load_unique_yaml_file


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "tmux/config.yml"


@dataclass(frozen=True)
class InventoryHost:
    name: str
    address: str


@dataclass(frozen=True)
class SessionConfig:
    name: str
    local_command: str
    remote_command: str


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a YAML mapping")
    return value


def load_config(config_path: Path) -> tuple[Path, str, str, dict[str, SessionConfig]]:
    raw = _require_mapping(load_unique_yaml_file(config_path), "Tmux config")
    if raw.get("schema_version") != 1:
        raise ValueError("tmux/config.yml must use schema_version 1")

    inventory = _require_mapping(raw.get("inventory"), "inventory")
    inventory_path = (config_path.parent / str(inventory["path"])).resolve()
    default_group = str(inventory["default_group"])
    default_user = str(inventory["default_user"])

    sessions_raw = _require_mapping(raw.get("sessions"), "sessions")
    sessions: dict[str, SessionConfig] = {}
    for mode, raw_values in sessions_raw.items():
        values = _require_mapping(raw_values, f"sessions.{mode}")
        sessions[mode] = SessionConfig(
            name=str(values["name"]),
            local_command=str(values["local_command"]),
            remote_command=str(values["remote_command"]),
        )
    return inventory_path, default_group, default_user, sessions


def load_inventory_group(inventory_path: Path, group: str) -> list[InventoryHost]:
    """Read direct group members and resolve their addresses from host declarations."""
    current_group: str | None = None
    addresses: dict[str, str] = {}
    members: list[str] = []

    for raw_line in inventory_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_group = line[1:-1]
            continue
        if current_group is None or current_group.endswith((":children", ":vars")):
            continue

        fields = shlex.split(line, comments=True)
        if not fields:
            continue
        hostname = fields[0]
        for field in fields[1:]:
            if field.startswith("ansible_host="):
                addresses[hostname] = field.split("=", 1)[1]
        if current_group == group and hostname not in members:
            members.append(hostname)

    if not members:
        raise ValueError(f"inventory group {group!r} has no direct hosts")

    missing = [hostname for hostname in members if hostname not in addresses]
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"hosts without ansible_host declarations: {names}")

    return [InventoryHost(name=name, address=addresses[name]) for name in members]


def tmux_commands(
    session: SessionConfig,
    hosts: list[InventoryHost],
    user: str,
) -> list[list[str]]:
    commands = [
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            session.name,
            "-n",
            "Local",
            "-c",
            str(REPO_ROOT),
            session.local_command,
        ]
    ]
    for host in hosts:
        ssh_command = shlex.join(
            ["ssh", "-t", f"{user}@{host.address}", session.remote_command]
        )
        commands.append(
            [
                "tmux",
                "new-window",
                "-d",
                "-t",
                session.name,
                "-n",
                host.name,
                ssh_command,
            ]
        )
    commands.append(["tmux", "attach-session", "-t", session.name])
    return commands


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", help="session mode defined in tmux/config.yml")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="session configuration file (default: tmux/config.yml)",
    )
    parser.add_argument("--group", help="override the configured inventory group")
    parser.add_argument("--user", help="override the configured SSH user")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print commands without creating a Tmux session or connecting",
    )
    return parser.parse_args()


def print_dry_run(
    session: SessionConfig,
    hosts: list[InventoryHost],
    group: str,
    user: str,
) -> None:
    print(f"Session: {session.name}")
    print(f"Inventory group: {group}")
    print(f"Local window: {session.local_command}")
    print("Remote windows:")
    for host in hosts:
        remote = shlex.join(
            ["ssh", "-t", f"{user}@{host.address}", session.remote_command]
        )
        print(f"  {host.name}: {remote}")
    print("Dry run: no Tmux session created and no SSH connection opened.")


def main() -> int:
    args = parse_args()
    inventory_path, default_group, default_user, sessions = load_config(
        args.config.resolve()
    )
    if args.mode not in sessions:
        choices = ", ".join(sorted(sessions))
        message = f"unknown session mode {args.mode!r}; choose one of: {choices}"
        raise SystemExit(message)
    group = args.group or default_group
    user = args.user or default_user
    hosts = load_inventory_group(inventory_path, group)
    commands = tmux_commands(sessions[args.mode], hosts, user)

    if args.dry_run:
        print_dry_run(sessions[args.mode], hosts, group, user)
        return 0

    session_name = sessions[args.mode].name
    existing = subprocess.run(
        ["tmux", "has-session", "-t", f"={session_name}"],
        check=False,
        capture_output=True,
    )
    if existing.returncode == 0:
        raise SystemExit(
            f"Tmux session {session_name!r} already exists; attach to or stop it first"
        )

    for command in commands:
        subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
