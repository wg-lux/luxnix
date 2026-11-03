"""Durable all-or-rollback publication of a generated file set.

An applying journal is an explicit incomplete-generation marker. Cooperating
readers take the same lock and recover it before reading generated files.
"""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path, content, mode):
    with path.open("xb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _replace(source, destination, mode):
    fd, name = tempfile.mkstemp(prefix=".autoconf-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            with source.open("rb") as original:
                shutil.copyfileobj(original, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, destination)
        _sync(destination.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def _recover(root):
    journal = root / ".autoconf-publication"
    if not journal.exists():
        return
    info = journal.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Unsafe generated publication journal")
    plan = json.loads((journal / "plan.json").read_text())
    if plan["state"] == "applying":
        for index, entry in enumerate(plan["entries"]):
            target = Path(entry["path"])
            if (
                not any(
                    target.is_relative_to(Path(p)) and target != Path(p)
                    for p in plan["roots"]
                )
                or target.resolve() != target
            ):
                raise ValueError("Unsafe generated publication journal")
            if target.exists():
                content = target.read_bytes()
                permitted = [
                    p.read_bytes()
                    for p in (journal / f"{index}.old", journal / f"{index}.new")
                    if p.exists()
                ]
                if content not in permitted:
                    raise ValueError(
                        "Generated output changed after interruption; retain journal for operator review"
                    )
            if entry["old_mode"] is None:
                target.unlink(missing_ok=True)
                _sync(target.parent)
            else:
                _replace(journal / f"{index}.old", target, entry["old_mode"])
    elif plan["state"] != "committed":
        raise ValueError("Unknown generated publication state")
    shutil.rmtree(journal)
    _sync(root)


@contextmanager
def publication_lock(root):
    """Serialize publication and recover incomplete output before any reads."""
    root = Path(root).absolute()
    root.mkdir(parents=True, exist_ok=True)
    if root.resolve() != root:
        raise ValueError("Generated publication root may not contain symlinks")
    fd = os.open(
        root / ".autoconf-publication.lock",
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
        0o600,
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            raise ValueError("Unsafe generated publication lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _recover(root)
        yield root
    finally:
        os.close(fd)


def publish_files(outputs, *, root=None, locked=False, allowed_roots=None):
    """Publish ``(path, bytes | None, mode)`` entries, rolling back on failure.

    None deletes a stale generated file within the same transaction. Journal
    state is durable before the first output change and until rollback or commit.
    """
    outputs = [(Path(p).absolute(), value, mode) for p, value, mode in outputs]
    if not outputs:
        return
    root = (
        Path(root).absolute()
        if root
        else Path(os.path.commonpath([str(p.parent) for p, _, _ in outputs]))
    )
    allowed_roots = tuple(Path(p).absolute() for p in (allowed_roots or (root,)))
    if not locked:
        with publication_lock(root):
            return publish_files(
                outputs, root=root, locked=True, allowed_roots=allowed_roots
            )
    targets = [p for p, _, _ in outputs]
    if len(set(targets)) != len(targets):
        raise ValueError("Duplicate generated publication destination")
    journal = root / ".autoconf-publication"
    if journal.exists():
        raise ValueError("Unrecovered generated publication journal")
    stage = Path(tempfile.mkdtemp(prefix=".autoconf-stage-", dir=root))
    try:
        entries = []
        for index, (target, content, mode) in enumerate(outputs):
            if (
                not any(target.is_relative_to(p) and target != p for p in allowed_roots)
                or target.resolve() != target
            ):
                raise ValueError("Unsafe generated output destination")
            target.parent.mkdir(parents=True, exist_ok=True)
            old_mode = None
            if target.exists():
                info = target.lstat()
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("Generated destination is not a regular file")
                old_mode = stat.S_IMODE(info.st_mode)
                _write(stage / f"{index}.old", target.read_bytes(), old_mode)
            if content is not None:
                _write(stage / f"{index}.new", content, mode)
            entries.append(
                dict(
                    path=str(target),
                    old_mode=old_mode,
                    mode=mode,
                    delete=content is None,
                )
            )
        plan = dict(
            state="applying", entries=entries, roots=[str(p) for p in allowed_roots]
        )
        _write(stage / "plan.json", json.dumps(plan).encode(), 0o600)
        _sync(stage)
        os.replace(stage, journal)
        _sync(root)
        try:
            for index, entry in enumerate(entries):
                target = Path(entry["path"])
                if entry["delete"]:
                    target.unlink(missing_ok=True)
                    _sync(target.parent)
                else:
                    _replace(journal / f"{index}.new", target, entry["mode"])
            plan["state"] = "committed"
            _write(journal / "committed.json", json.dumps(plan).encode(), 0o600)
            os.replace(journal / "committed.json", journal / "plan.json")
            _sync(journal)
        except BaseException:
            _recover(root)
            raise
        _recover(root)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
