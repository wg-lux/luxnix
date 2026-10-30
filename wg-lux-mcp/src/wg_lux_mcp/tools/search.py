from __future__ import annotations

import ast
import re
from pathlib import Path

from ..repo import resolve_repo, run_readonly
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


def _tracked_files(root: Path, suffixes: set[str] | None = None) -> list[Path]:
    raw = run_readonly(root, ["git", "ls-files", "-z"])
    root = root.resolve()
    paths: list[Path] = []
    for relative in raw.split("\0"):
        if not relative:
            continue
        path = root / relative
        if suffixes is not None and path.suffix.lower() not in suffixes:
            continue
        try:
            resolved = path.resolve()
            if root not in resolved.parents or path.is_symlink():
                continue
            if resolved.is_file() and resolved.stat().st_size <= MAX_FILE_BYTES:
                paths.append(resolved)
        except OSError:
            continue
    return paths


def _query_terms(query: str) -> list[str]:
    terms = list(dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_.-]{1,}", query.lower())))
    if not terms:
        raise ValueError("query must contain at least one searchable term")
    return terms[:12]


def _source(
    repo: str, root: Path, path: Path, commit: str, start: int, end: int
) -> dict[str, object]:
    return {
        "repo": repo,
        "path": str(path.relative_to(root)),
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
    matches: list[tuple[int, str, int, str, Path]] = []

    for path in _tracked_files(root, SEARCHABLE_SUFFIXES):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        relative = str(path.relative_to(root)).lower()
        for number, line in enumerate(lines, start=1):
            lowered = line.lower()
            matched = sum(term in lowered for term in terms)
            path_matches = sum(term in relative for term in terms)
            if matched:
                score = matched * 10 + path_matches * 3
                matches.append((score, relative, number, line.strip()[:240], path))

    matches.sort(key=lambda item: (-item[0], item[1], item[2]))
    hits = [
        {
            "summary": snippet,
            "score": score,
            "sources": [_source(repo, root, path, commit, number, number)],
        }
        for score, _, number, snippet, path in matches[:max_results]
    ]
    return {"query": query, "repo": repo, "matches": hits, "truncated": len(matches) > max_results}


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

    for path in _tracked_files(root, {".py"}):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for qualified, node in _qualified_definitions(tree):
            if qualified.lower() == expected or node.name.lower() == expected:
                end = getattr(node, "end_lineno", node.lineno)
                hits.append(
                    {
                        "symbol": qualified,
                        "kind": type(node).__name__.removesuffix("Def").lower(),
                        "summary": ast.get_docstring(node, clean=True)
                        or f"Definition of {qualified}",
                        "sources": [_source(repo, root, path, commit, node.lineno, end)],
                    }
                )
    hits.sort(key=lambda hit: (str(hit["sources"][0]["path"]), str(hit["symbol"])))  # type: ignore[index]
    return {
        "repo": repo,
        "symbol": symbol,
        "matches": hits[:max_results],
        "truncated": len(hits) > max_results,
    }


def get_related_tests(repo: str, path: str, max_results: int = 20) -> dict[str, object]:
    """Find tracked test files related by filename or source-path references."""
    if not 1 <= max_results <= 50:
        raise ValueError("max_results must be between 1 and 50")
    root = resolve_repo(repo)
    requested = (root / path).resolve()
    if requested != root and root not in requested.parents:
        raise ValueError("Path escapes repository root")
    commit = repository_commit(repo, root)
    stem = requested.stem.lower()
    module = str(requested.relative_to(root).with_suffix("")).replace("/", ".").lower()
    hits: list[tuple[int, Path, str]] = []

    for candidate in _tracked_files(root, {".py"}):
        relative = str(candidate.relative_to(root)).lower()
        if not (candidate.name.startswith("test_") or "/tests/" in f"/{relative}"):
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        score = (10 if stem in candidate.stem.lower() else 0) + (5 if module in text.lower() else 0)
        score += 3 if stem in text.lower() else 0
        if score:
            reason = (
                "matching test filename"
                if stem in candidate.stem.lower()
                else "references source module"
            )
            hits.append((score, candidate, reason))

    hits.sort(key=lambda item: (-item[0], str(item[1])))
    results = [
        {
            "summary": reason,
            "score": score,
            "sources": [_source(repo, root, candidate, commit, 1, 1)],
        }
        for score, candidate, reason in hits[:max_results]
    ]
    return {"repo": repo, "path": path, "matches": results, "truncated": len(hits) > max_results}
