from __future__ import annotations

import fcntl
import os
import shutil
import time
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


def _ensure_disk_capacity(*, destination_dir: Path, required_bytes: int) -> None:
    if required_bytes < 0:
        raise ValueError("required_bytes must not be negative")
    available_bytes = shutil.disk_usage(destination_dir).free
    if available_bytes < required_bytes:
        raise OSError(
            f"Insufficient disk space in {destination_dir}: "
            f"required={required_bytes} available={available_bytes}",
        )


def _temporary_destination(destination: Path) -> Path:
    return destination.with_name(
        f".{destination.name}.tmp.{os.getpid()}.{uuid4().hex}",
    )


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _prepare_destination(
    destination: Path,
    *,
    required_bytes: int | None,
    dir_mode: int | None,
) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if dir_mode is not None:
        os.chmod(target.parent, dir_mode)
    if required_bytes is not None:
        _ensure_disk_capacity(
            destination_dir=target.parent,
            required_bytes=required_bytes,
        )
    return target


def _write_temporary_file(
    destination: Path,
    *,
    content: Iterable[bytes],
    file_mode: int | None,
) -> Path:
    temporary = _temporary_destination(destination)
    try:
        with temporary.open("xb") as handle:
            if file_mode is not None:
                os.chmod(temporary, file_mode)
            for chunk in content:
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary
    except Exception:
        safe_unlink_file(temporary)
        raise


def atomic_write_file(
    *,
    destination: Path,
    content: Iterable[bytes],
    required_bytes: int | None = None,
    file_mode: int | None = None,
    dir_mode: int | None = None,
) -> Path:
    """Write and atomically replace one local file."""
    target = _prepare_destination(
        destination,
        required_bytes=required_bytes,
        dir_mode=dir_mode,
    )
    temporary = _write_temporary_file(
        target,
        content=content,
        file_mode=file_mode,
    )
    try:
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    except Exception:
        safe_unlink_file(temporary)
        raise
    return target


def atomic_create_file(
    *,
    destination: Path,
    content: Iterable[bytes],
    required_bytes: int | None = None,
    file_mode: int | None = None,
    dir_mode: int | None = None,
) -> Path:
    """Create one local file atomically without replacing an existing path."""
    target = _prepare_destination(
        destination,
        required_bytes=required_bytes,
        dir_mode=dir_mode,
    )
    temporary = _write_temporary_file(
        target,
        content=content,
        file_mode=file_mode,
    )
    try:
        os.link(temporary, target)
        safe_unlink_file(temporary)
        _fsync_directory(target.parent)
    except Exception:
        safe_unlink_file(temporary)
        raise
    return target


def safe_unlink_file(path: Path, *, missing_ok: bool = True) -> None:
    """Remove one filesystem entry without following it."""
    Path(path).unlink(missing_ok=missing_ok)


@contextmanager
def advisory_file_lock(
    *,
    lock_path: Path,
    timeout_seconds: float = 90.0,
    poll_interval_seconds: float = 0.05,
) -> Generator[None]:
    """Hold a process-owned advisory lock for the duration of the context."""
    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must not be negative")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be greater than zero")

    target = Path(lock_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        target,
        os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    acquired = False
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for advisory lock: {target}")
                time.sleep(poll_interval_seconds)

        os.ftruncate(descriptor, 0)
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
