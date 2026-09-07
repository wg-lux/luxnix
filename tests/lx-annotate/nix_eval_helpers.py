"""Portable Nix evaluation helpers shared by lx-annotate contract tests."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import subprocess
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FLAKE_URI_PLACEHOLDER = "__LUXNIX_FLAKE_URI__"
REPO_FLAKE_URI = f"git+file://{REPO_ROOT}"


def _resolve_repo_flake(expr: str) -> str:
    return expr.replace(FLAKE_URI_PLACEHOLDER, REPO_FLAKE_URI)


@lru_cache(maxsize=None)
def eval_json(expr: str) -> Any:
    """Evaluate a Nix expression as JSON from the current repository."""
    result = subprocess.run(
        [
            "nix",
            "eval",
            "--impure",
            "--json",
            "--expr",
            _resolve_repo_flake(expr),
            "--show-trace",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def eval_result(expr: str) -> subprocess.CompletedProcess[str]:
    """Evaluate a Nix expression while preserving an expected failure result."""
    return subprocess.run(
        [
            "nix",
            "eval",
            "--impure",
            "--expr",
            _resolve_repo_flake(expr),
            "--show-trace",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
