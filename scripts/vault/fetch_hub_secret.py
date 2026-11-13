#!/usr/bin/env python3
"""Fetch one hub KV v2 field into a prepared target file, keeping the last accepted value.

The caller (managed-secrets or luxnix-hub-secrets) owns the atomic rename of the
target over the deployed file. This helper only decides what the target holds:

* a fresh, validated value whose KV version is not older than the last accepted one;
* during a hub outage (unreachable, sealed, no runtime token) and only with
  --tolerate-outage: the bytes of the previously deployed file;
* otherwise nothing, with a nonzero exit so the deployed file stays untouched.

Values are never printed, hashed or written anywhere except the target. The state
file holds only the KV path, the accepted version and timestamps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

NAME = re.compile(r"[A-Za-z0-9_.-]+")
KV_PATH = re.compile(r"[A-Za-z0-9_-]+(/[A-Za-z0-9_.-]+)+")
OUTAGE_STATES = {"vault-unreachable", "vault-sealed", "auth-unavailable"}


class Rejected(Exception):
    """The hub answered, but the answer must not be deployed."""


def classify(classifier: str | None, stderr: bytes) -> str:
    if classifier is None:
        return "vault-error"
    with tempfile.NamedTemporaryFile(prefix="hub-secret-error.") as handle:
        handle.write(stderr)
        handle.flush()
        result = subprocess.run(
            [classifier, handle.name], capture_output=True, text=True, check=False
        )
    state = result.stdout.strip()
    return state if result.returncode == 0 and state else "vault-error"


def read_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise Rejected(f"unreadable delivery state {path}: {error}") from error
    if not isinstance(state, dict):
        raise Rejected(f"malformed delivery state {path}")
    return state


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(state, handle, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


def write_target(target: Path, content: bytes) -> None:
    # The caller created the target privately; never widen it and never follow links.
    descriptor = os.open(target, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


def previous_content(previous: Path | None) -> bytes | None:
    if previous is None:
        return None
    try:
        descriptor = os.open(previous, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        content = handle.read()
    return content or None


def fetch(args: argparse.Namespace, recorded: dict) -> tuple[bytes, int]:
    if not os.environ.get("VAULT_TOKEN"):
        raise Outage("auth-unavailable")
    try:
        result = subprocess.run(
            [args.cli, "kv", "get", "-format=json", args.kv_path],
            capture_output=True,
            check=False,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise Outage("vault-unreachable") from error
    if result.returncode != 0:
        state = classify(args.classifier, result.stderr)
        if state in OUTAGE_STATES:
            raise Outage(state)
        if b"No value found at" in result.stderr:
            raise Rejected("the hub holds no secret at this path yet")
        raise Rejected(f"hub request failed (state: {state})")
    try:
        document = json.loads(result.stdout)
        value = document["data"]["data"][args.field]
        version = document["data"]["metadata"]["version"]
    except (ValueError, KeyError, TypeError) as error:
        raise Rejected("hub response lacks the expected field or version") from error
    if not isinstance(value, str) or not isinstance(version, int) or version < 1:
        raise Rejected("hub response has an invalid field or version type")
    if args.strip_newlines:
        value = value.replace("\n", "")
    if not value.strip():
        raise Rejected("hub returned an empty value")
    accepted = recorded.get("version")
    if (
        recorded.get("kv_path") == args.kv_path
        and isinstance(accepted, int)
        and version < accepted
    ):
        raise Rejected(
            f"hub returned version {version}, older than accepted version {accepted}; "
            "after a reviewed KV reset remove the delivery state file"
        )
    return value.encode("utf-8"), version


class Outage(Exception):
    """The hub cannot be asked right now; nothing is known about the secret."""


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True)
    parser.add_argument("--kv-path", required=True, help="<mount>/<path> as used by kv get")
    parser.add_argument("--field", required=True)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--previous", type=Path, help="currently deployed file")
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--cli", default="vault", help="Vault-compatible client binary")
    parser.add_argument("--classifier", help="luxnix-vault-classify-auth-error executable")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--strip-newlines", action="store_true")
    parser.add_argument(
        "--tolerate-outage",
        action="store_true",
        help="keep the deployed value while the hub is unreachable, sealed or unauthenticated",
    )
    parser.add_argument(
        "--empty-when-unavailable",
        action="store_true",
        help="without a usable value write an empty target and succeed (optional secrets)",
    )
    args = parser.parse_args(argv)
    if not NAME.fullmatch(args.name):
        parser.error("--name must match [A-Za-z0-9_.-]+")
    if not KV_PATH.fullmatch(args.kv_path) or ".." in args.kv_path:
        parser.error("--kv-path must be <mount>/<path> without traversal")
    if not args.field or not NAME.fullmatch(args.field):
        parser.error("--field must match [A-Za-z0-9_.-]+")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse(sys.argv[1:] if argv is None else argv)
    state_file = args.state_dir / f"{args.name}.json"
    now = int(time.time())
    try:
        recorded = read_state(state_file)
        content, version = fetch(args, recorded)
    except Outage as outage:
        kept = previous_content(args.previous) if args.tolerate_outage else None
        if kept is not None:
            write_target(args.target, kept)
            write_state(
                state_file,
                {**recorded, "status": "degraded", "reason": str(outage), "checked_at": now},
            )
            print(
                f"BLOCKER: hub secret {args.name} not refreshed (state: {outage}); "
                f"keeping accepted version {recorded.get('version', 'unknown')}.",
                file=sys.stderr,
            )
            return 0
        reason = f"hub unavailable (state: {outage})"
    except Rejected as rejected:
        reason = str(rejected)
    else:
        write_target(args.target, content)
        write_state(
            state_file,
            {
                "kv_path": args.kv_path,
                "version": version,
                "status": "current",
                "accepted_at": now,
                "checked_at": now,
            },
        )
        print(f"Hub secret {args.name}: accepted version {version}.")
        return 0

    if args.empty_when_unavailable:
        write_target(args.target, b"")
        print(f"WARNING: hub secret {args.name} is unavailable: {reason}.", file=sys.stderr)
        return 0
    print(f"ERROR: hub secret {args.name} was not deployed: {reason}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
