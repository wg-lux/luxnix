from __future__ import annotations

import os
import re
import selectors
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import settings


class RepositoryError(RuntimeError):
    pass


GIT_EXECUTABLE = shutil.which("git")
MAX_TREE_BYTES = 16_000_000
SENSITIVE_PARTS = {
    ".git",
    ".ssh",
    ".gnupg",
    ".luxnix-recovery",
    "secrets",
    "private",
    "cmdb",
}
SENSITIVE_NAMES = {
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "credentials.yml",
    "credentials.yaml",
    "tokens.json",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".age", ".vault", ".kdbx", ".enc"}


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


def git_bytes(repo: Path, argv: list[str], limit: int, *, prefix: bool = False) -> bytes:
    """Bound subprocess output while reading; internal callers never parse truncation."""
    if not argv or argv[0] != "git":
        raise RepositoryError("Only read-only Git commands are supported")
    if GIT_EXECUTABLE is None:
        raise RepositoryError("Git executable was not found in the service PATH")
    command = [
        GIT_EXECUTABLE,
        "--no-pager",
        "--no-optional-locks",
        "--literal-pathspecs",
        "-c",
        "core.fsmonitor=false",
        *argv[1:],
    ]
    process = subprocess.Popen(
        command,
        cwd=repo,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=dict(os.environ, GIT_NO_REPLACE_OBJECTS="1"),
    )
    stream = process.stdout
    if stream is None:
        process.kill()
        process.wait()
        raise RepositoryError("Git output pipe was not created")
    output = bytearray()
    deadline = time.monotonic() + settings.command_timeout_s
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(stream, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RepositoryError("Read-only Git command timed out")
                if not selector.select(remaining):
                    raise RepositoryError("Read-only Git command timed out")
                chunk = os.read(stream.fileno(), min(65_536, limit + 1 - len(output)))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > limit:
                    if prefix:
                        return bytes(output[:limit])
                    raise RepositoryError(
                        "Git output exceeds its limit; no partial result was used"
                    )
        code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        if code:
            raise RepositoryError(f"Read-only Git command failed with exit code {code}")
        return bytes(output)
    except subprocess.TimeoutExpired as exc:
        raise RepositoryError("Read-only Git command timed out") from exc
    finally:
        stream.close()
        if process.poll() is None:
            process.kill()
        process.wait()


def run_readonly(repo: Path, argv: list[str]) -> str:
    """Return a complete bounded response or an explicit limit error."""
    output = git_bytes(repo, argv, settings.max_output_chars * 4).decode("utf-8")
    if len(output) > settings.max_output_chars:
        raise RepositoryError("Git output exceeds its response limit; no partial result was used")
    return output


def public_path(relative: str) -> str:
    """Validate the separate outbound policy before any repository content read."""
    path = PurePosixPath(relative)
    if (
        not relative
        or not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in relative
        or "\x00" in relative
        or str(path) != relative
    ):
        raise ValueError("Path escapes repository root or is not a canonical relative path")
    parts = [part.lower() for part in path.parts]
    if (
        any(part in SENSITIVE_PARTS or part == ".env" or part.startswith(".env.") for part in parts)
        or parts[-1] in SENSITIVE_NAMES
        or path.suffix.lower() in SENSITIVE_SUFFIXES
    ):
        raise RepositoryError("Sensitive repository path is not available through MCP")
    return relative


def repository_commit(root: Path) -> str:
    return run_readonly(root, ["git", "rev-parse", "--verify", "HEAD^{commit}"]).strip()


@dataclass(frozen=True)
class CommittedFile:
    path: str
    blob: str
    size: int


def committed_files(root: Path, commit: str, relative: str | None = None) -> list[CommittedFile]:
    args = ["git", "ls-tree", "-r", "-l", "-z", commit]
    if relative is not None:
        args += ["--", public_path(relative)]
    raw = git_bytes(root, args, MAX_TREE_BYTES)
    result = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, blob, size = metadata.split()
        if mode not in {b"100644", b"100755"} or kind != b"blob":
            continue  # Symlinks and submodules are never exposed as file content.
        try:
            path = public_path(name.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RepositoryError):
            continue
        result.append(CommittedFile(path, blob.decode("ascii"), int(size)))
    return result


def read_blob(root: Path, file: CommittedFile, max_bytes: int, *, prefix: bool = False) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40,64}", file.blob):
        raise RepositoryError("Invalid committed blob identity")
    return git_bytes(root, ["git", "cat-file", "blob", file.blob], max_bytes, prefix=prefix)
