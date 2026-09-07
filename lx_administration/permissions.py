"""Canonical permissions for private LuxNix runtime artifacts."""

import os
from pathlib import Path
import tempfile


PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def ensure_private_directory(path: str | Path) -> Path:
    """Create a directory and enforce the canonical private mode."""
    directory = Path(path).expanduser()
    directory.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
    directory.chmod(PRIVATE_DIRECTORY_MODE)
    return directory


def write_private_text(path: str | Path, value: str) -> None:
    """Atomically write private text without following a target symlink."""
    target = Path(path).expanduser()
    if target.is_symlink():
        raise OSError(f"Refusing to write private text through symlink: {target}")

    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.stem}.",
        suffix=target.suffix,
        text=True,
    )
    temporary = Path(temporary_name)

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as private_file:
            os.fchmod(private_file.fileno(), PRIVATE_FILE_MODE)
            private_file.write(value)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
