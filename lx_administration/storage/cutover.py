"""Background pre-copy and short-stop cutover into encrypted storage.

Data moves into newly provisioned containers while
the application keeps running, and only the final delta needs a short stop.

precopy  Writers keep running. rsync repeatedly into a private staging copy
         next to the destination. The staging copy is never trusted as final;
         it only shortens the stop window.
cutover  The caller has stopped every writer. A final rsync with --delete
         and --checksum makes the staging copy exact, a dry run must report no
         difference, the staging payload is renamed into place, and a receipt
         is written. Only then may the caller activate binds and start writers.

Sources are never modified or deleted. A populated destination is adopted only
when it is already identical; it is never overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import subprocess


class CutoverError(RuntimeError):
    pass


@dataclass(frozen=True)
class Item:
    source: Path
    destination: Path
    excludes: tuple[str, ...] = ()

    @property
    def stage(self) -> Path:
        return Path(str(self.destination) + ".luxnix-copy")

    @property
    def payload(self) -> Path:
        return self.stage / "data"

    @property
    def plan(self) -> dict:
        return {"source": str(self.source), "destination": str(self.destination)}


def run(*args: str) -> bytes:
    result = subprocess.run(args, capture_output=True, check=False)
    if result.returncode:
        # rsync diagnostics can contain private file names.
        raise CutoverError(f"{args[0]} failed (exit {result.returncode}); sources retained")
    return result.stdout


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".pending")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def rsync(item: Item, target: Path, *, dry: bool) -> bytes:
    # --delete only ever applies to the private staging payload or a dry run.
    args = ["rsync", "-aHAXx", "--numeric-ids", "--checksum", "--delete"]
    if dry:
        args += ["--dry-run", "--itemize-changes", "--out-format=%i"]
    for path in item.excludes:
        args += ["--exclude=/" + path + "/***"]
    return run(*args, str(item.source) + "/", str(target) + "/")


def _open_stage(item: Item) -> None:
    stage = item.stage
    if stage.exists():
        info = os.lstat(stage)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise CutoverError("Untrusted staging directory")
        plan = stage / "plan.json"
        if plan.is_symlink() or not plan.is_file() or json.loads(plan.read_text()) != item.plan:
            raise CutoverError("Staging copy belongs to another migration")
    else:
        stage.mkdir(mode=0o700, parents=True)
        atomic_json(stage / "plan.json", item.plan)
    if item.payload.is_symlink():
        raise CutoverError("Staging payload must not be a symlink")
    item.payload.mkdir(mode=0o700, exist_ok=True)


def _check_source(item: Item) -> None:
    if not item.source.is_dir() or item.source.is_symlink():
        raise CutoverError("Migration source must be an existing real directory")


def precopy(item: Item) -> bool:
    """Refresh the staging copy while writers run. Returns True when no copy is needed."""
    _check_source(item)
    if item.destination.exists():
        return True
    _open_stage(item)
    rsync(item, item.payload, dry=False)
    return False


def cutover(item: Item, receipt: Path, identity) -> None:
    """Final exact copy; the caller guarantees that every writer is stopped.

    identity(source, destination) returns the receipt content after the rename.
    """
    _check_source(item)
    if item.destination.exists():
        # Adopt an identical destination only; a differing one is never overwritten.
        if rsync(item, item.destination, dry=True).strip():
            raise CutoverError("Existing encrypted destination differs; refusing overwrite")
    else:
        _open_stage(item)
        rsync(item, item.payload, dry=False)
        if rsync(item, item.payload, dry=True).strip():
            raise CutoverError("Final copy verification failed; sources retained")
        run("sync", "-f", str(item.payload))
        if item.destination.exists():
            raise CutoverError("Destination appeared while copying")
        item.payload.rename(item.destination)
        (item.stage / "plan.json").unlink()
        item.stage.rmdir()
    atomic_json(receipt, identity(item.source, item.destination))


def stop_writers(writers: list[str]) -> list[str]:
    """Stop writers that are active; return them so a failed cutover can restart them."""
    active = [
        name
        for name in writers
        if run("systemctl", "show", "--value", "-p", "ActiveState", name + ".service").strip()
        in (b"active", b"activating", b"reloading")
    ]
    if active:
        try:
            run("systemctl", "stop", *[name + ".service" for name in active])
        except CutoverError:
            # A multi-unit stop can partially succeed. Restore the original
            # active set before propagating the failure to the caller.
            restart_writers(active)
            raise
    return active


def restart_writers(writers: list[str]) -> None:
    # Binds are not active before a receipt exists, so writers resume on the unchanged sources.
    if writers:
        run("systemctl", "start", *[name + ".service" for name in writers])
