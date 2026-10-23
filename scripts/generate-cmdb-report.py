#!/usr/bin/env python3
"""Render a private, deliberately small inventory report from local facts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import json
import math
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
    observed_at: str
    observation_age: str


def _text(value: JsonValue, fallback: str = "unknown") -> str:
    if value is None or value == "":
        return fallback
    if not isinstance(value, str):
        raise ReportError("invalid fact field: expected text")
    return value


def _positive_number(value: JsonValue, *, integer: bool = False) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ReportError("invalid numeric fact field")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ReportError("invalid numeric fact field") from exc
    if (
        not math.isfinite(number)
        or number <= 0
        or (integer and not number.is_integer())
    ):
        raise ReportError("invalid numeric fact field")
    return number


def _observation(facts: JsonObject, now: datetime) -> tuple[str, str]:
    date_time = facts.get("ansible_date_time")
    if date_time is None:
        return "unknown", "unknown"
    if not isinstance(date_time, dict):
        raise ReportError("invalid observation timestamp")
    epoch = _positive_number(date_time.get("epoch"))
    if epoch is None:
        return "unknown", "unknown"
    try:
        observed = datetime.fromtimestamp(epoch, tz=timezone.utc)
    except (ValueError, OverflowError, OSError) as exc:
        raise ReportError("invalid observation timestamp") from exc
    age = (now - observed).total_seconds()
    age_text = (
        f"{int(age)} seconds at generation"
        if age >= 0
        else "clock skew: observation is in the future"
    )
    return observed.isoformat(), age_text


def _valid_result(result: JsonObject) -> JsonObject | None:
    if any(
        key in result and result[key] is not False for key in ("failed", "unreachable")
    ):
        return None
    facts = result.get("ansible_facts")
    return facts if isinstance(facts, dict) and facts else None


def _facts_for_host(data: JsonValue, host_name: str) -> JsonObject:
    if isinstance(data, dict):
        if any(
            key in data and data[key] is not False for key in ("failed", "unreachable")
        ):
            raise ReportError(f"invalid local fact snapshot: {host_name}")
        direct_facts = _valid_result(data)
        if direct_facts is not None:
            return direct_facts

        results = data.get(host_name)
        if (
            isinstance(results, list)
            and len(results) == 1
            and isinstance(results[0], dict)
        ):
            wrapped_facts = _valid_result(results[0])
            if wrapped_facts is not None:
                return wrapped_facts

    raise ReportError(f"invalid local fact snapshot: {host_name}")


def _summary(path: Path, now: datetime) -> HostSummary:
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

    ram_mb = _positive_number(facts.get("ansible_memtotal_mb"))
    ram_gib = f"{ram_mb / 1024:.1f}" if ram_mb is not None else "unknown"
    vcpus = _positive_number(
        facts.get("ansible_processor_vcpus", facts.get("ansible_processor_cores")),
        integer=True,
    )
    observed_at, observation_age = _observation(facts, now)

    return HostSummary(
        name=host_name,
        operating_system=distribution,
        architecture=architecture,
        virtualization=virtualization,
        vcpus=str(int(vcpus)) if vcpus is not None else "unknown",
        ram_gib=ram_gib,
        observed_at=observed_at,
        observation_age=observation_age,
    )


def load_summaries(facts_dir: Path, now: datetime) -> list[HostSummary]:
    fact_files = sorted(facts_dir.glob("*.json"))
    if not fact_files:
        raise ReportError(
            "no local facts found; run: devenv tasks run autoconf:refresh-facts"
        )
    return [_summary(path, now) for path in fact_files]


def render_html(hosts: list[HostSummary], now: datetime) -> str:
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
                host.observed_at,
                host.observation_age,
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
  <p>Generated at {escape(now.isoformat())}.</p>
  <p class="note">Static inventory snapshot, not live health or availability.
    Failed refreshes retain last-known-good observations. Ages are measured at report
    generation and do not update while viewing. Observation timestamps come from
    host-reported facts; unknown timestamps cannot establish freshness. No clinical
    freshness threshold is inferred. Hosts without snapshots are absent from
    this report.</p>
  <table>
    <caption>LuxNix inventory</caption>
    <thead>
      <tr>
        <th>Host</th><th>Operating system</th><th>Architecture</th>
        <th>Virtualization</th><th>vCPUs</th><th>RAM (GiB)</th>
        <th>Observed at (UTC)</th><th>Observation age</th>
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
        now = datetime.now(timezone.utc)
        hosts = load_summaries(facts_dir, now)
        write_private_report(output, render_html(hosts, now))
    except ReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Generated private redacted report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
