from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import settings


class RepositoryError(RuntimeError):
    pass


GIT_EXECUTABLE = shutil.which("git")


def resolve_repo(name: str) -> Path:
    try:
        path = settings.repositories[name]
    except KeyError as exc:
        allowed = ", ".join(sorted(settings.repositories))
        raise RepositoryError(f"Unknown repository {name!r}; allowed: {allowed}") from exc

    path = path.resolve()
    if not path.is_dir():
        raise RepositoryError(f"Repository path does not exist: {path}")
    if not (path / ".git").exists():
        raise RepositoryError(f"Not a Git repository: {path}")
    return path


def run_readonly(repo: Path, argv: list[str]) -> str:
    """Run a fixed, read-only command without a shell."""
    if not argv or argv[0] != "git":
        raise RepositoryError("Only read-only Git commands are supported")
    if GIT_EXECUTABLE is None:
        raise RepositoryError("Git executable was not found in the service PATH")

    result = subprocess.run(
        argv,
        executable=GIT_EXECUTABLE,
        cwd=repo,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=settings.command_timeout_s,
        check=False,
    )
    output = result.stdout[: settings.max_output_chars]
    if result.returncode != 0:
        raise RepositoryError(
            f"Command failed with exit code {result.returncode}: {' '.join(argv)}\n{output}"
        )
    return output
