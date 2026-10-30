from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NIXTEST_ARGS = ["--workers", "1"]
DEFAULT_TIMEOUT_SECONDS = 3600


def _nixtest_args() -> list[str]:
    raw_args = os.environ.get("LUXNIX_NIXTEST_ARGS")
    if raw_args:
        return shlex.split(raw_args)

    return DEFAULT_NIXTEST_ARGS


def _timeout_seconds() -> int:
    raw_timeout = os.environ.get("LUXNIX_NIXTEST_TIMEOUT_SECONDS")
    if raw_timeout:
        return int(raw_timeout)

    return DEFAULT_TIMEOUT_SECONDS


def _tail(output: str | bytes | None, line_count: int = 120) -> str:
    if not output:
        return "<empty>"

    if isinstance(output, bytes):
        output = output.decode(errors="replace")

    return "\n".join(output.splitlines()[-line_count:])


def test_nixtest_suite_passes() -> None:
    """Run the flake-exposed nixtest suite through pytest."""
    if shutil.which("nix") is None:
        pytest.skip("nix is not available")

    command = ["nix", "run", ".#nixtests", "--", *_nixtest_args()]

    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=_timeout_seconds(),
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            "\n".join(
                [
                    f"nixtest command timed out after {exc.timeout} seconds: {shlex.join(command)}",
                    "",
                    "stdout tail:",
                    _tail(exc.stdout),
                    "",
                    "stderr tail:",
                    _tail(exc.stderr),
                ]
            )
        )

    assert result.returncode == 0, "\n".join(
        [
            f"nixtest command failed with exit code {result.returncode}: {shlex.join(command)}",
            "",
            "stdout tail:",
            _tail(result.stdout),
            "",
            "stderr tail:",
            _tail(result.stderr),
        ]
    )
