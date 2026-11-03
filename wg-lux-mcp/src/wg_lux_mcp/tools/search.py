from __future__ import annotations

import ast
import re
from pathlib import Path

from ..repo import (
    CommittedFile,
    RepositoryError,
    committed_files,
    public_path,
    read_blob,
    resolve_repo,
)
from .repos import repository_commit

MAX_FILE_BYTES = 1_000_000
SEARCHABLE_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".nix",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}


def _tracked_files(root: Path, commit: str, suffixes: set[str]) -> tuple[list[CommittedFile], int]:
    files = [f for f in committed_files(root, commit) if Path(f.path).suffix.lower() in suffixes]
    skipped = sum(f.size > MAX_FILE_BYTES for f in files)
    selected = [f for f in files if f.size <= MAX_FILE_BYTES]
    if sum(f.size for f in selected) > 64_000_000:
        raise RepositoryError("Search exceeds its 64 MB scan budget; no partial result was used")
    return selected, skipped


def _text(root: Path, file: CommittedFile) -> str:
    data = read_blob(root, file, MAX_FILE_BYTES)
    if b"\0" in data:
        raise UnicodeDecodeError("utf-8", data, 0, 1, "binary content")
    return data.decode("utf-8")


def _query_terms(query: str) -> list[str]:
    terms = list(dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_.-]{1,}", query.lower())))
    if not terms:
        raise ValueError("query must contain at least one searchable term")
    return terms[:12]


def _source(repo: str, file: CommittedFile, commit: str, start: int, end: int) -> dict[str, object]:
    return {
        "repo": repo,
        "path": file.path,
        "blob": file.blob,
        "commit": commit,
        "lines": [start, end],
    }


def search_code(repo: str, query: str, max_results: int = 20) -> dict[str, object]:
    """Rank compact code matches and return line-level provenance."""
    if not 1 <= max_results <= 50:
        raise ValueError("max_results must be between 1 and 50")
    terms = _query_terms(query)
    root = resolve_repo(repo)
    commit = repository_commit(repo, root)
    matches: list[tuple[int, str, int, str, CommittedFile]] = []
    files, skipped = _tracked_files(root, commit, SEARCHABLE_SUFFIXES)
    match_count = 0

    for path in files:
        try:
            lines = _text(root, path).splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.path.lower()
        for number, line in enumerate(lines, start=1):
            lowered = line.lower()
            matched = sum(term in lowered for term in terms)
            path_matches = sum(term in relative for term in terms)
            if matched:
                score = matched * 10 + path_matches * 3
                match_count += 1
                matches.append((score, relative, number, line.strip()[:240], path))
                if len(matches) >= max_results * 2:
                    matches.sort(key=lambda item: (-item[0], item[1], item[2]))
                    del matches[max_results:]

    matches.sort(key=lambda item: (-item[0], item[1], item[2]))
    hits = [
        {
            "summary": snippet,
            "score": score,
            "sources": [_source(repo, path, commit, number, number)],
        }
        for score, _, number, snippet, path in matches[:max_results]
    ]
    return {
        "query": query,
        "repo": repo,
        "matches": hits,
        "truncated": match_count > max_results,
        "skipped_large_files": skipped,
        "commit": commit,
    }


def _qualified_definitions(
    tree: ast.AST,
) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]]:
    found: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append((node.name, node))
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        found.append((f"{node.name}.{child.name}", child))
    return found


def find_symbol(repo: str, symbol: str, max_results: int = 20) -> dict[str, object]:
    """Locate Python definitions by simple or class-qualified symbol name."""
    if not symbol.strip() or len(symbol) > 200:
        raise ValueError("symbol must contain between 1 and 200 characters")
    if not 1 <= max_results <= 50:
        raise ValueError("max_results must be between 1 and 50")
    root = resolve_repo(repo)
    commit = repository_commit(repo, root)
    expected = symbol.strip().lower()
    hits: list[dict[str, object]] = []

    files, skipped = _tracked_files(root, commit, {".py"})
    for path in files:
        try:
            tree = ast.parse(_text(root, path), filename=path.path)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for qualified, node in _qualified_definitions(tree):
            if qualified.lower() == expected or node.name.lower() == expected:
                end = getattr(node, "end_lineno", node.lineno)
                hits.append(
                    {
                        "symbol": qualified,
                        "kind": type(node).__name__.removesuffix("Def").lower(),
                        "summary": (
                            ast.get_docstring(node, clean=True) or f"Definition of {qualified}"
                        )[:500],
                        "sources": [_source(repo, path, commit, node.lineno, end)],
                    }
                )
    hits.sort(key=lambda hit: (str(hit["sources"][0]["path"]), str(hit["symbol"])))  # type: ignore[index]
    return {
        "repo": repo,
        "symbol": symbol,
        "matches": hits[:max_results],
        "truncated": len(hits) > max_results,
        "skipped_large_files": skipped,
        "commit": commit,
    }


def get_related_tests(repo: str, path: str, max_results: int = 20) -> dict[str, object]:
    """Find tracked test files related by filename or source-path references."""
    if not 1 <= max_results <= 50:
        raise ValueError("max_results must be between 1 and 50")
    root = resolve_repo(repo)
    requested = Path(public_path(path))
    commit = repository_commit(repo, root)
    stem = requested.stem.lower()
    module = str(requested.with_suffix("")).replace("/", ".").lower()
    hits: list[tuple[int, CommittedFile, str]] = []

    files, skipped = _tracked_files(root, commit, {".py"})
    for candidate in files:
        relative = candidate.path.lower()
        if not (Path(candidate.path).name.startswith("test_") or "/tests/" in f"/{relative}"):
            continue
        try:
            text = _text(root, candidate)
        except (OSError, UnicodeDecodeError):
            continue
        score = (10 if stem in Path(candidate.path).stem.lower() else 0) + (
            5 if module in text.lower() else 0
        )
        score += 3 if stem in text.lower() else 0
        if score:
            reason = (
                "matching test filename"
                if stem in Path(candidate.path).stem.lower()
                else "references source module"
            )
            hits.append((score, candidate, reason))

    hits.sort(key=lambda item: (-item[0], item[1].path))
    results = [
        {
            "summary": reason,
            "score": score,
            "sources": [_source(repo, candidate, commit, 1, 1)],
        }
        for score, candidate, reason in hits[:max_results]
    ]
    return {
        "repo": repo,
        "path": path,
        "matches": results,
        "truncated": len(hits) > max_results,
        "skipped_large_files": skipped,
        "commit": commit,
    }
