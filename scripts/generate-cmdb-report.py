#!/usr/bin/env python3
"""Render a private, deliberately small inventory report from local facts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import escape
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
type JsonObject = dict[str, JsonValue]


class ReportError(ValueError):
    """Raised when a safe report cannot be generated."""


@dataclass(frozen=True)
class HostSummary:
    name: str
    operating_system: str
    architecture: str
    virtualization: str
    vcpus: str
    ram_gib: str


def _text(value: JsonValue, fallback: str = "unknown") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _facts_for_host(data: JsonValue, host_name: str) -> JsonObject:
    if isinstance(data, dict):
        direct_facts = data.get("ansible_facts")
        if isinstance(direct_facts, dict):
            return direct_facts

        results = data.get(host_name)
        if (
            isinstance(results, list)
            and len(results) == 1
            and isinstance(results[0], dict)
        ):
            wrapped_facts = results[0].get("ansible_facts")
            if isinstance(wrapped_facts, dict):
                return wrapped_facts

    raise ReportError(f"invalid local fact snapshot: {host_name}")


def _summary(path: Path) -> HostSummary:
    host_name = path.stem
    try:
        data = cast("JsonValue", json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"could not read local fact snapshot: {host_name}") from exc

    facts = _facts_for_host(data, host_name)
    distribution = (
        " ".join(
            part
            for part in (
                _text(facts.get("ansible_distribution"), ""),
                _text(facts.get("ansible_distribution_version"), ""),
            )
            if part
        )
        or "unknown"
    )
    architecture = (
        " / ".join(
            part
            for part in (
                _text(facts.get("ansible_architecture"), ""),
                _text(facts.get("ansible_userspace_architecture"), ""),
            )
            if part
        )
        or "unknown"
    )
    virtualization = (
        " / ".join(
            part
            for part in (
                _text(facts.get("ansible_virtualization_type"), ""),
                _text(facts.get("ansible_virtualization_role"), ""),
            )
            if part
        )
        or "unknown"
    )

    ram_mb = facts.get("ansible_memtotal_mb")
    if isinstance(ram_mb, (int, float, str)) and not isinstance(ram_mb, bool):
        try:
            ram_gib = f"{float(ram_mb) / 1024:.1f}"
        except ValueError:
            ram_gib = "unknown"
    else:
        ram_gib = "unknown"

    return HostSummary(
        name=host_name,
        operating_system=distribution,
        architecture=architecture,
        virtualization=virtualization,
        vcpus=_text(
            facts.get("ansible_processor_vcpus", facts.get("ansible_processor_cores"))
        ),
        ram_gib=ram_gib,
    )


def load_summaries(facts_dir: Path) -> list[HostSummary]:
    fact_files = sorted(facts_dir.glob("*.json"))
    if not fact_files:
        raise ReportError(
            "no local facts found; run: devenv tasks run autoconf:refresh-facts"
        )
    return [_summary(path) for path in fact_files]


def render_html(hosts: list[HostSummary]) -> str:
    rows = "\n".join(
        "<tr>"
        + "".join(
            f"<td>{escape(value)}</td>"
            for value in (
                host.name,
                host.operating_system,
                host.architecture,
                host.virtualization,
                host.vcpus,
                host.ram_gib,
            )
        )
        + "</tr>"
        for host in hosts
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LuxNix inventory</title>
  <style>
    body {{ color: #202124; font: 16px/1.5 system-ui, sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #c7c7c7; padding: .5rem; text-align: left; }}
    th {{ background: #f1f3f4; }}
    caption {{
      font-size: 1.4rem;
      font-weight: 600;
      margin-bottom: 1rem;
      text-align: left;
    }}
    .note {{ color: #555; }}
  </style>
</head>
<body>
  <table>
    <caption>LuxNix inventory</caption>
    <thead>
      <tr>
        <th>Host</th><th>Operating system</th><th>Architecture</th>
        <th>Virtualization</th><th>vCPUs</th><th>RAM (GiB)</th>
      </tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <p class="note">
    Redacted local report. Addresses, serials, environment values, inventory
    variables, and full host facts are intentionally excluded.
  </p>
</body>
</html>
"""


def write_private_report(output: Path, content: str) -> None:
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.parent.chmod(0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent, prefix=f".{output.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a private, redacted HTML report from local facts."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Autoconf configuration (default: project Autoconf config)",
    )
    parser.add_argument(
        "--facts-dir",
        type=Path,
        help="fact snapshots (default: paths.ansible_root/cmdb)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="report destination (default: paths.report_output)",
    )
    return parser.parse_args(argv)


def resolve_report_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.facts_dir is not None and args.output is not None:
        return args.facts_dir.resolve(), args.output.resolve()

    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from lx_administration.autoconf import (
            DEFAULT_CONFIG_PATH,
            AutoconfConfig,
        )

        config = AutoconfConfig.load(args.config or DEFAULT_CONFIG_PATH)
    except (ImportError, ValueError) as exc:
        raise ReportError(f"could not load Autoconf configuration: {exc}") from exc

    facts_dir = (args.facts_dir or config.facts_dir).resolve()
    output = (args.output or config.report_output).resolve()
    return facts_dir, output


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        facts_dir, output = resolve_report_paths(args)
        hosts = load_summaries(facts_dir)
        write_private_report(output, render_html(hosts))
    except ReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Generated private redacted report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
