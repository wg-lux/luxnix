#!/usr/bin/env python3
"""Run the repository's checks and record a machine-readable state snapshot.

The snapshot is meant to be captured immediately before and after a disruptive
change - most often a ``nix flake update`` or a Nixpkgs channel bump - so the
two files can be diffed to see exactly what the change moved. See
``docs/nixos-version-bump.md``.

Checks are grouped into categories so slow steps can be opted out of:

    python-tests   uv run pytest -q               (the repository suite)
    nix-quality    scripts/nix-quality.py         (ratcheted parse/lint/lock)
    nixtests       nix run .#nixtests             (VM and contract nixtests)
    host-eval      nix eval <toplevel drvPath>    (evaluate every exported host)
    host-build     nix build --no-link            (no-link build of every host)
    flake-check    nix flake check --no-build

By default every category except ``host-build`` and ``flake-check`` runs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LAYOUT_PATH = REPO_ROOT / "tests/layout.yml"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "repo-state"

CATEGORY_ORDER = [
    "python-tests",
    "nix-quality",
    "nixtests",
    "host-eval",
    "host-build",
    "flake-check",
]
DEFAULT_CATEGORIES = ["python-tests", "nix-quality", "nixtests", "host-eval"]

# Nixpkgs release branches stop receiving updates roughly seven months after
# release; flake-checker warns once an input is older than this many days.
MAX_RECOMMENDED_INPUT_AGE_DAYS = 30


def run(
    command: list[str], *, timeout: int | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def tail(text: str, limit: int = 40) -> str:
    lines = text.strip().splitlines()
    return "\n".join(lines[-limit:])


def now_utc() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def git_output(*args: str) -> str:
    return run(["git", *args]).stdout.strip()


def exported_hosts() -> list[str]:
    result = run(
        [
            "nix",
            "eval",
            "--json",
            ".#nixosConfigurations",
            "--apply",
            "builtins.attrNames",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(f"could not list nixosConfigurations:\n{tail(result.stderr)}")
    return sorted(json.loads(result.stdout))


def repo_state() -> dict[str, Any]:
    lock = json.loads((REPO_ROOT / "flake.lock").read_text(encoding="utf-8"))
    nodes = lock.get("nodes", {})
    root_inputs = nodes.get("root", {}).get("inputs", {})
    inputs: dict[str, Any] = {}
    for name in ("nixpkgs", "nixpkgs-unstable"):
        # The root input name is not always the node key (e.g. the top-level
        # `nixpkgs` frequently resolves to a node like `nixpkgs_8`).
        node_key = root_inputs.get(name, name)
        locked = nodes.get(node_key, {}).get("locked")
        if not locked:
            continue
        last_modified = locked.get("lastModified")
        age_days = None
        if last_modified is not None:
            age_days = round(
                (now_utc().timestamp() - last_modified) / 86400, 1
            )
        inputs[name] = {
            "rev": locked.get("rev"),
            "ref": locked.get("ref"),
            "last_modified": last_modified,
            "age_days": age_days,
            "outdated": age_days is not None
            and age_days > MAX_RECOMMENDED_INPUT_AGE_DAYS,
        }

    status = git_output("status", "--porcelain")
    changed = [line for line in status.splitlines() if line.strip()]
    return {
        "timestamp": now_utc().isoformat(),
        "git": {
            "branch": git_output("rev-parse", "--abbrev-ref", "HEAD"),
            "head": git_output("rev-parse", "HEAD"),
            "head_subject": git_output("log", "-1", "--pretty=%s"),
            "dirty": bool(changed),
            "changed_files": len(changed),
        },
        "flake_inputs": inputs,
        "flake_checker_issue_count": flake_checker_issue_count(),
        "devenv_version": (run(["devenv", "version"]).stdout.strip() or None),
        "exported_host_count": _safe_host_count(),
    }


def _safe_host_count() -> int | None:
    try:
        return len(exported_hosts())
    except (RuntimeError, json.JSONDecodeError):
        return None


def flake_checker_issue_count() -> int | None:
    result = run(
        [
            "flake-checker",
            "--no-telemetry",
            "--check-outdated",
            "--check-owner",
            "--check-supported",
            "--nixpkgs-keys",
            "nixpkgs,nixpkgs-unstable",
            "flake.lock",
        ]
    )
    for line in (result.stdout + result.stderr).splitlines():
        if "discovered" in line and "issue" in line:
            for token in line.split():
                if token.isdigit():
                    return int(token)
    return None


def check(
    name: str,
    category: str,
    command: list[str],
    timeout: int | None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    location = f" (in {cwd.relative_to(REPO_ROOT)})" if cwd else ""
    print(f"  → {name}: {' '.join(command)}{location}", flush=True)
    started = time.monotonic()
    try:
        completed = run(command, timeout=timeout, cwd=cwd)
        returncode = completed.returncode
        output = completed.stdout + completed.stderr
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        output = (exc.output or "") + f"\n[timed out after {timeout}s]"
    duration = round(time.monotonic() - started, 1)
    passed = returncode == 0
    print(f"    {'ok' if passed else 'FAIL'} ({duration}s)", flush=True)
    result: dict[str, Any] = {
        "name": name,
        "category": category,
        "command": command,
        "status": "passed" if passed else "failed",
        "returncode": returncode,
        "duration_seconds": duration,
    }
    if not passed:
        result["output_tail"] = tail(output)
    return result


def _step(
    name: str,
    category: str,
    command: list[str],
    *,
    timeout: int | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "category": category,
        "command": command,
        "timeout": timeout,
        "cwd": cwd,
    }


def planned_checks(categories: list[str], host_timeout: int) -> list[dict[str, Any]]:
    uv = ["uv", "run", "--no-sync"]
    plan: list[dict[str, Any]] = []

    if "python-tests" in categories:
        layout = yaml.safe_load(LAYOUT_PATH.read_text(encoding="utf-8"))
        for suite in layout.get("python_suites", []):
            if suite["id"] == "cuda-probes":
                continue  # optional hardware probe, not a pass/fail suite
            plan.append(
                _step(
                    f"python:{suite['id']}",
                    "python-tests",
                    [*uv, "pytest", "-q", suite["path"]],
                )
            )
        for project in layout.get("independent_projects", []):
            # A nested project resolves its own dependencies, so run pytest from
            # its own root with a plain `uv run` (no --no-sync).
            project_dir = REPO_ROOT / Path(project["path"]).parts[0]
            plan.append(
                _step(
                    f"python:{project['id']}",
                    "python-tests",
                    ["uv", "run", "pytest", "-q"],
                    cwd=project_dir,
                )
            )

    if "nix-quality" in categories:
        # Fast mode only: the ratcheted parse/lint/lockfile gate. Full flake
        # evaluation is the separate `flake-check` category.
        plan.append(
            _step("nix-quality", "nix-quality", [*uv, "python", "scripts/nix-quality.py"])
        )

    if "nixtests" in categories:
        plan.append(
            _step("nixtests", "nixtests", ["nix", "run", ".#nixtests", "--", "--workers", "1"])
        )

    if "host-eval" in categories or "host-build" in categories:
        try:
            hosts = exported_hosts()
        except RuntimeError:
            hosts = []
        for host in hosts:
            attr = f".#nixosConfigurations.{host}.config.system.build.toplevel"
            if "host-eval" in categories:
                plan.append(
                    _step(
                        f"host-eval:{host}",
                        "host-eval",
                        ["nix", "eval", "--raw", f"{attr}.drvPath"],
                        timeout=host_timeout,
                    )
                )
            if "host-build" in categories:
                plan.append(
                    _step(
                        f"host-build:{host}",
                        "host-build",
                        ["nix", "build", "--no-link", attr],
                        timeout=host_timeout,
                    )
                )

    if "flake-check" in categories:
        plan.append(
            _step("flake-check", "flake-check", ["nix", "flake", "check", "--no-build"])
        )

    return plan


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--categories",
        default=",".join(DEFAULT_CATEGORIES),
        help=(
            "comma-separated subset of "
            f"{','.join(CATEGORY_ORDER)} (default: {','.join(DEFAULT_CATEGORIES)})"
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="run every category, including host-build and flake-check",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"directory for the snapshot file (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="optional label recorded in the snapshot (e.g. 'before-flake-update')",
    )
    parser.add_argument(
        "--host-timeout",
        type=int,
        default=1800,
        help="per-host eval/build timeout in seconds (default: 1800)",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="print the summary but do not write a snapshot file",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.all:
        categories = list(CATEGORY_ORDER)
    else:
        categories = [item.strip() for item in args.categories.split(",") if item.strip()]
    unknown = [item for item in categories if item not in CATEGORY_ORDER]
    if unknown:
        print(f"unknown categories: {', '.join(unknown)}", file=sys.stderr)
        return 2
    categories = [item for item in CATEGORY_ORDER if item in categories]

    print(f"repo-state-summary: {', '.join(categories)}")
    print("Collecting repository state ...")
    state = repo_state()

    print("Running checks ...")
    results = [
        check(
            step["name"],
            step["category"],
            step["command"],
            step["timeout"],
            step["cwd"],
        )
        for step in planned_checks(categories, args.host_timeout)
    ]

    failed = [r for r in results if r["status"] == "failed"]
    snapshot = {
        "schema_version": 1,
        "label": args.label,
        "categories": categories,
        "repository_state": state,
        "checks": results,
        "totals": {
            "checks": len(results),
            "passed": len(results) - len(failed),
            "failed": len(failed),
        },
    }

    if not args.no_write:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
        suffix = f"-{args.label}" if args.label else ""
        target = args.output_dir / f"repo-state-{stamp}{suffix}.json"
        target.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "latest.json").write_text(
            json.dumps(snapshot, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nSnapshot written to {target.relative_to(REPO_ROOT)}")

    print("\n=== Repository state ===")
    git = state["git"]
    print(f"  branch {git['branch']} @ {git['head'][:12]} ({'dirty' if git['dirty'] else 'clean'})")
    for name, info in state["flake_inputs"].items():
        flag = "  OUTDATED" if info["outdated"] else ""
        print(f"  {name}: {str(info['rev'])[:12]} age {info['age_days']}d{flag}")
    print(f"  flake-checker issues: {state['flake_checker_issue_count']}")

    print("\n=== Checks ===")
    for result in results:
        marker = "PASS" if result["status"] == "passed" else "FAIL"
        print(f"  [{marker}] {result['name']} ({result['duration_seconds']}s)")
    print(
        f"\n{snapshot['totals']['passed']}/{snapshot['totals']['checks']} checks passed"
    )

    if failed:
        print("\nFailing checks:")
        for result in failed:
            print(f"\n--- {result['name']} (exit {result['returncode']}) ---")
            print(result.get("output_tail", ""))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
