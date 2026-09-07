from __future__ import annotations

from pathlib import Path

from ..config import settings
from ..repo import resolve_repo, run_readonly


def list_repositories() -> list[str]:
    return sorted(settings.repositories)


def get_repo_status(repo: str) -> dict[str, object]:
    path = resolve_repo(repo)
    branch = run_readonly(path, ["git", "branch", "--show-current"]).strip()
    head = run_readonly(path, ["git", "rev-parse", "HEAD"]).strip()
    status = run_readonly(path, ["git", "status", "--porcelain=v1"])
    return {
        "repo": repo,
        "path": str(path),
        "branch": branch,
        "head": head,
        "clean": not bool(status.strip()),
        "status": status.splitlines(),
    }


def get_recent_commits(repo: str, limit: int = 10) -> list[dict[str, str]]:
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    path = resolve_repo(repo)
    raw = run_readonly(
        path,
        ["git", "log", f"-{limit}", "--date=iso-strict", "--format=%H%x1f%ad%x1f%an%x1f%s"],
    )
    result: list[dict[str, str]] = []
    for line in raw.splitlines():
        commit, date, author, subject = line.split("\x1f", 3)
        result.append({"commit": commit, "date": date, "author": author, "subject": subject})
    return result


def read_text_file(repo: str, relative_path: str, max_chars: int = 20_000) -> dict[str, object]:
    if not 1 <= max_chars <= 40_000:
        raise ValueError("max_chars must be between 1 and 40000")

    root = resolve_repo(repo)
    requested = (root / relative_path).resolve()
    if requested != root and root not in requested.parents:
        raise ValueError("Path escapes repository root")
    if not requested.is_file():
        raise FileNotFoundError(relative_path)

    data = requested.read_text(encoding="utf-8")
    return {
        "repo": repo,
        "path": str(requested.relative_to(root)),
        "truncated": len(data) > max_chars,
        "text": data[:max_chars],
    }


def get_pyproject(repo: str) -> dict[str, object]:
    root = resolve_repo(repo)
    path = root / "pyproject.toml"
    if not path.is_file():
        return {"repo": repo, "exists": False, "text": None}
    text = path.read_text(encoding="utf-8")
    return {"repo": repo, "exists": True, "text": text[:40_000]}


def inspect_django_migrations(repo: str, app: str) -> list[str]:
    if not app.isascii() or not app.isidentifier():
        raise ValueError("app must be a simple Python identifier")

    root = resolve_repo(repo)
    matches = sorted(root.glob(f"**/{app}/migrations/[0-9][0-9][0-9][0-9]_*.py"))
    return [str(path.relative_to(root)) for path in matches[:500]]


def repository_commit(repo: str, root: Path | None = None) -> str:
    return run_readonly(root or resolve_repo(repo), ["git", "rev-parse", "HEAD"]).strip()
