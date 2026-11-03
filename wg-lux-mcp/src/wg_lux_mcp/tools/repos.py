from __future__ import annotations

import codecs
import re
from pathlib import Path, PurePosixPath

from ..config import settings
from ..repo import (
    RepositoryError,
    committed_files,
    public_path,
    read_blob,
    resolve_repo,
    run_readonly,
)
from ..repo import repository_commit as _commit


def list_repositories() -> list[str]:
    return sorted(settings.repositories)


def get_repo_status(repo: str) -> dict[str, object]:
    path = resolve_repo(repo)
    branch = run_readonly(path, ["git", "branch", "--show-current"]).strip()
    head = _commit(path)
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
        path, ["git", "log", f"-{limit}", "--date=iso-strict", "--format=%H%x1f%ad%x1f%an%x1f%s"]
    )
    result: list[dict[str, str]] = []
    for line in raw.splitlines():
        commit, date, author, subject = line.split("\x1f", 3)
        result.append({"commit": commit, "date": date, "author": author, "subject": subject})
    return result


def read_text_file(repo: str, relative_path: str, max_chars: int = 20_000) -> dict[str, object]:
    if not 1 <= max_chars <= 40_000:
        raise ValueError("max_chars must be between 1 and 40000")
    public_path(relative_path)
    root = resolve_repo(repo)
    commit = _commit(root)
    files = [f for f in committed_files(root, commit, relative_path) if f.path == relative_path]
    if not files:
        raise FileNotFoundError("Path is not a public regular file in the selected commit")
    file = files[0]
    # A Unicode character occupies at most four bytes. Ignore only an incomplete
    # last codepoint when a byte-bounded prefix cuts through its UTF-8 encoding.
    limit = (max_chars + 1) * 4
    raw = read_blob(root, file, limit, prefix=True)
    decoder = codecs.getincrementaldecoder("utf-8")()
    text = decoder.decode(raw, final=file.size <= limit)
    return {
        "repo": repo,
        "path": file.path,
        "commit": commit,
        "blob": file.blob,
        "truncated": file.size > len(raw) or len(text) > max_chars,
        "text": text[:max_chars],
    }


def get_pyproject(repo: str) -> dict[str, object]:
    try:
        result = read_text_file(repo, "pyproject.toml", max_chars=40_000)
    except FileNotFoundError:
        return {"repo": repo, "exists": False, "text": None}
    return result | {"exists": True}


def inspect_django_migrations(repo: str, app: str) -> list[str]:
    if not app.isascii() or not app.isidentifier():
        raise ValueError("app must be a simple Python identifier")
    root = resolve_repo(repo)
    matches = [
        f.path
        for f in committed_files(root, _commit(root))
        if PurePosixPath(f.path).parts[-3:-1] == (app, "migrations")
        and re.fullmatch(r"[0-9]{4}_.+\.py", PurePosixPath(f.path).name)
    ]
    if len(matches) > 500:
        raise RepositoryError("Migration listing exceeds 500 entries; no partial result was used")
    return sorted(matches)


def repository_commit(repo: str, root: Path | None = None) -> str:
    return _commit(root or resolve_repo(repo))
