#!/usr/bin/env python3
"""Run the reproducible, ratcheted Nix quality checks for Luxnix."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, TextIO

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_policy(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        policy = yaml.safe_load(handle)
    if not isinstance(policy, dict) or policy.get("schema_version") != 1:
        raise ValueError(f"{path} must contain schema_version: 1")
    return policy


def nix_files(policy: dict[str, Any]) -> list[Path]:
    scope = policy["scope"]
    excluded = set(scope["exclude_directories"])
    suffix = scope["include_suffix"]
    return sorted(
        path
        for path in REPO_ROOT.rglob(f"*{suffix}")
        if not any(part in excluded for part in path.relative_to(REPO_ROOT).parts)
        and not is_excluded(str(path.relative_to(REPO_ROOT)), policy)
    )


def is_excluded(path: str, policy: dict[str, Any]) -> bool:
    return any(
        fnmatch.fnmatch(path, pattern)
        for pattern in policy["scope"].get("exclude_files", [])
    )


def is_generated(path: str, policy: dict[str, Any]) -> bool:
    scope = policy["scope"]
    excluded_from_generated = any(
        fnmatch.fnmatch(path, pattern)
        for pattern in scope.get("generated_exclude_patterns", [])
    )
    return not excluded_from_generated and any(
        fnmatch.fnmatch(path, pattern) for pattern in scope["generated_patterns"]
    )


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def decode_json_stream(raw: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    documents: list[dict[str, Any]] = []
    offset = 0
    while offset < len(raw):
        while offset < len(raw) and raw[offset].isspace():
            offset += 1
        if offset >= len(raw):
            break
        document, offset = decoder.raw_decode(raw, offset)
        documents.append(document)
    return documents


def accepted(
    result: subprocess.CompletedProcess[str], definition: dict[str, Any]
) -> bool:
    return result.returncode in definition["accepted_exit_codes"]


def check_nix_parse(policy: dict[str, Any], files: list[Path]) -> dict[str, Any]:
    definition = policy["checks"]["nix_parse"]
    relative_files = [str(path.relative_to(REPO_ROOT)) for path in files]
    result = run([*definition["command"], *relative_files])
    return {
        "command_ok": accepted(result, definition),
        "exit_code": result.returncode,
        "parsed_files": len(files) if accepted(result, definition) else 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def check_flake_source_visibility(policy: dict[str, Any]) -> dict[str, Any]:
    """Report files that Git-backed flakes would omit from their source tree."""
    definition = policy["checks"]["flake_source_visibility"]
    roots = policy["scope"]["flake_source_roots"]
    result = run([*definition["command"], *roots])
    untracked_files = sorted(
        line for line in result.stdout.splitlines() if line.strip()
    )
    return {
        "command_ok": accepted(result, definition),
        "exit_code": result.returncode,
        "untracked_files": len(untracked_files),
        "files": untracked_files,
        "stderr": result.stderr.strip(),
    }


def count_deadnix(policy: dict[str, Any]) -> dict[str, Any]:
    definition = policy["checks"]["deadnix"]
    result = run(definition["command"])
    documents = decode_json_stream(result.stdout)
    findings = [
        {"file": document["file"].removeprefix("./"), **finding}
        for document in documents
        for finding in document["results"]
        if not is_excluded(document["file"].removeprefix("./"), policy)
    ]
    return {
        "command_ok": accepted(result, definition),
        "exit_code": result.returncode,
        "findings": len(findings),
        "details": findings,
        "non_generated_findings": sum(
            not is_generated(item["file"], policy) for item in findings
        ),
        "stderr": result.stderr.strip(),
    }


def count_statix(policy: dict[str, Any]) -> dict[str, Any]:
    definition = policy["checks"]["statix"]
    result = run(definition["command"])
    documents = decode_json_stream(result.stdout)
    findings = [
        {"file": document["file"].removeprefix("./"), **finding}
        for document in documents
        for finding in document["report"]
        if not is_excluded(document["file"].removeprefix("./"), policy)
    ]
    by_rule: dict[str, int] = {}
    for finding in findings:
        rule = f"W{finding['code']}"
        by_rule[rule] = by_rule.get(rule, 0) + 1
    return {
        "command_ok": accepted(result, definition),
        "exit_code": result.returncode,
        "findings": len(findings),
        "details": findings,
        "non_generated_findings": sum(
            not is_generated(item["file"], policy) for item in findings
        ),
        "by_rule": dict(sorted(by_rule.items())),
        "stderr": result.stderr.strip(),
    }


def count_nixfmt(policy: dict[str, Any], files: list[Path]) -> dict[str, Any]:
    definition = policy["checks"]["nixfmt"]
    command = [
        policy["formatter"]["command"],
        "--check",
        *[str(path.relative_to(REPO_ROOT)) for path in files],
    ]
    result = run(command)
    unformatted = [
        line.removesuffix(": not formatted").removeprefix("./")
        for line in result.stderr.splitlines()
        if line.endswith(": not formatted")
    ]
    return {
        "command_ok": accepted(result, definition),
        "exit_code": result.returncode,
        "unformatted_files": len(unformatted),
        "files": unformatted,
        "non_generated_unformatted_files": sum(
            not is_generated(path, policy) for path in unformatted
        ),
        "stderr": "\n".join(
            line
            for line in result.stderr.splitlines()
            if not line.endswith(": not formatted")
        ),
    }


def count_flake_checker(policy: dict[str, Any]) -> dict[str, Any]:
    definition = policy["checks"]["flake_checker"]
    # GitHub Actions switches the tool to annotation-only output without the
    # summary count. Use the same parseable text contract locally and in CI.
    result = run(["env", "-u", "GITHUB_ACTIONS", *definition["command"]])
    combined = f"{result.stdout}\n{result.stderr}"
    counts = re.findall(r"discovered (\d+) issues?\b", combined)
    clean = (
        "The flake checker scanned your flake.lock and didn't identify any issues."
        in combined
    )
    parse_ok = (len(counts) == 1 and not clean) or (not counts and clean)
    issues = (int(counts[0]) if counts else 0) if parse_ok else None
    outdated_inputs = [
        {"input": input_name, "age_days": int(age_days)}
        for input_name, age_days in re.findall(
            r"> The ([^\s]+) input is (\d+) days old", combined
        )
    ]
    return {
        "command_ok": accepted(result, definition) and parse_ok,
        "exit_code": result.returncode,
        "issues": issues,
        "parse_error": (
            None if parse_ok else "Missing or ambiguous flake-checker summary"
        ),
        "outdated_inputs": outdated_inputs,
        "output": combined.strip(),
    }


def check_flake(policy: dict[str, Any]) -> dict[str, Any]:
    definition = policy["checks"]["flake_evaluation"]
    result = run(definition["command"])
    return {
        "command_ok": accepted(result, definition),
        "exit_code": result.returncode,
        "output": f"{result.stdout}\n{result.stderr}".strip(),
    }


def evaluate_baselines(
    report: dict[str, Any], policy: dict[str, Any], full: bool
) -> list[str]:
    failures: list[str] = []
    checks = policy["checks"]
    comparisons = [
        (
            "flake_source_visibility",
            "untracked_files",
            "max_untracked_files",
        ),
        ("deadnix", "findings", "max_findings"),
        ("deadnix", "non_generated_findings", "max_non_generated_findings"),
        ("statix", "findings", "max_findings"),
        ("statix", "non_generated_findings", "max_non_generated_findings"),
        ("nixfmt", "unformatted_files", "max_unformatted_files"),
        (
            "nixfmt",
            "non_generated_unformatted_files",
            "max_non_generated_unformatted_files",
        ),
    ]
    comparisons.append(("flake_checker", "issues", "max_issues"))
    for check_name, metric, baseline_name in comparisons:
        actual = report[check_name][metric]
        maximum = checks[check_name]["baseline"][baseline_name]
        if actual is None:
            failures.append(f"{check_name}.{metric} has no validated result")
        elif actual > maximum:
            failures.append(
                f"{check_name}.{metric}={actual} exceeds baseline {maximum}"
            )
    for check_name, result in report.items():
        if (
            isinstance(result, dict)
            and "command_ok" in result
            and not result["command_ok"]
        ):
            failures.append(
                f"{check_name}: {result['parse_error']}"
                if result.get("parse_error")
                else f"{check_name} exited unexpectedly with {result['exit_code']}"
            )
    return failures


def diagnostic_location(path: str, position: dict[str, Any]) -> str:
    """Use the tool's coordinates; some error reports contain only a message."""
    line = position.get("line")
    column = position.get("column")
    if line is None:
        return path
    if column is None:
        return f"{path}:{line}"
    return f"{path}:{line}:{column}"


def print_diagnostics(
    report: dict[str, Any], stream: TextIO, *, verbose: bool = False
) -> None:
    """Print retained diagnostics without rerunning checks or changing counts."""
    untracked = report["flake_source_visibility"].get("files", [])
    if untracked:
        print("\nFlake source visibility: untracked files:", file=stream)
        for path in sorted(untracked):
            print(f"  {path}", file=stream)

    deadnix_details = report["deadnix"].get("details", [])
    if deadnix_details:
        print("\ndeadnix diagnostics:", file=stream)
        for finding in sorted(deadnix_details, key=lambda item: item["file"]):
            location = diagnostic_location(finding["file"], finding)
            message = finding.get("message") or "Unused declaration"
            print(f"  {location}: {message}", file=stream)

    statix_details = report["statix"].get("details", [])
    if statix_details:
        print("\nstatix diagnostics:", file=stream)
        for finding in sorted(statix_details, key=lambda item: item["file"]):
            # A Statix report can contain several source locations. Keep each
            # location visible, but continue counting reports, not locations.
            code = finding.get("code")
            severity = str(finding.get("severity", "Warn")).lower()
            prefix = {"warn": "W", "error": "E", "hint": "I"}.get(severity, "W")
            rule = f"[{prefix}{code}] " if code is not None else ""
            note = finding.get("note") or ""
            for diagnostic in finding.get("diagnostics") or [{}]:
                position = (diagnostic.get("at") or {}).get("from") or {}
                location = diagnostic_location(finding["file"], position)
                message = diagnostic.get("message") or note or "Lint finding"
                if note and note != message:
                    message = f"{note}: {message}"
                print(f"  {location}: {rule}{message}", file=stream)

    unformatted = report["nixfmt"].get("files", [])
    if unformatted:
        print("\nnixfmt: unformatted files:", file=stream)
        for path in sorted(unformatted):
            print(f"  {path}: not formatted", file=stream)

    for check_name, result in report.items():
        if not isinstance(result, dict):
            continue

        # Commands with unstructured output should also be shown when their
        # metrics fail, even if the policy accepts their process exit code.
        show_output = (
            verbose
            or not result.get("command_ok", True)
            or (check_name == "flake_checker" and bool(result.get("issues")))
        )
        output = result.get("output") if show_output else None
        if output:
            print(f"\n{check_name} output:\n{output}", file=stream)

        stdout = result.get("stdout") if show_output else None
        if stdout:
            print(f"\n{check_name} stdout:\n{stdout}", file=stream)

        # Preserve warnings/errors even when the exit code was accepted.
        # nixfmt's ordinary 'not formatted' lines are already printed above.
        stderr = result.get("stderr")
        if stderr:
            print(f"\n{check_name} stderr:\n{stderr}", file=stream)


def print_human(
    report: dict[str, Any],
    failures: list[str],
    full: bool,
    *,
    verbose: bool = False,
) -> None:
    deadnix_non_generated = report["deadnix"]["non_generated_findings"]
    statix_non_generated = report["statix"]["non_generated_findings"]
    print(f"Nix quality ({'full' if full else 'fast'})")
    print(f"  files: {report['files']}")
    print(
        "  flake source visibility: "
        f"{report['flake_source_visibility']['untracked_files']} untracked files"
    )
    print(f"  nix parse: {report['nix_parse']['parsed_files']} files")
    print(
        "  deadnix: "
        f"{report['deadnix']['findings']} findings "
        f"({deadnix_non_generated} outside generated host/home files)"
    )
    print(
        "  statix: "
        f"{report['statix']['findings']} findings "
        f"({statix_non_generated} outside generated host/home files)"
    )
    print(
        f"  nixfmt: {report['nixfmt']['unformatted_files']} unformatted files "
        "("
        f"{report['nixfmt']['non_generated_unformatted_files']} "
        "outside generated files)"
    )
    print(f"  flake-checker: {report['flake_checker']['issues']} issues")
    if full:
        flake_status = (
            "passed" if report["flake_evaluation"]["command_ok"] else "failed"
        )
        print(f"  flake evaluation: {flake_status}")
    if failures:
        # Keep the summary before stderr diagnostics in merged hook logs.
        sys.stdout.flush()
        print("Quality gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print_diagnostics(report, sys.stderr, verbose=verbose)
    else:
        if verbose:
            print_diagnostics(report, sys.stdout, verbose=True)
        print("Quality gate passed; no metric exceeded its ratcheted baseline.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "nix-quality.yml")
    parser.add_argument("--full", action="store_true", help="also run nix flake check")
    parser.add_argument(
        "--json", action="store_true", help="emit the complete report as JSON"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show detailed diagnostics even when the gate passes (human output only)",
    )
    args = parser.parse_args()

    policy = load_policy(args.config)
    files = nix_files(policy)
    report: dict[str, Any] = {
        "schema_version": 1,
        "mode": "full" if args.full else "fast",
        "files": len(files),
        "flake_source_visibility": check_flake_source_visibility(policy),
        "nix_parse": check_nix_parse(policy, files),
        "deadnix": count_deadnix(policy),
        "statix": count_statix(policy),
        "nixfmt": count_nixfmt(policy, files),
        "flake_checker": count_flake_checker(policy),
    }
    if args.full:
        report["flake_evaluation"] = check_flake(policy)
    failures = evaluate_baselines(report, policy, args.full)
    report["passed"] = not failures
    report["failures"] = failures
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report, failures, args.full, verbose=args.verbose)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
