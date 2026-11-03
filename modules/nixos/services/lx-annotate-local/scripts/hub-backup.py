"""Quiesce hub writers around one fresh database/media capture; recover on failure."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

from secret_storage import encrypted_storage


def validate_paths(spec: dict) -> list[str]:
    root = Path(spec["protected_root"])
    source = Path(spec["source"])
    destinations = [Path(p) for p in spec["destinations"]]
    for path in [root, source, *destinations]:
        if not path.is_absolute() or ".." in path.parts or path.resolve() != path:
            raise ValueError(
                "Backup paths must be absolute without symlinks or traversal"
            )
        if not path.is_relative_to(root):
            raise ValueError("Backup paths must remain on protected runtime storage")
        encrypted_storage(path)
    for index, destination in enumerate(destinations):
        if source.is_relative_to(destination):
            raise ValueError("Backup destination must not contain the source")
        if any(
            destination.is_relative_to(other) or other.is_relative_to(destination)
            for other in destinations[index + 1 :]
        ):
            raise ValueError("Backup destinations must not overlap")
    return [
        "/" + p.relative_to(source).as_posix() + "/"
        for p in destinations
        if p.is_relative_to(source)
    ]


def run(*args: str, timeout: int | None = 300) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Hub backup command failed: {args[0]}")
    return result.stdout.strip()


def save(path: Path, state: dict) -> None:
    temporary = path.with_suffix(".pending")
    with temporary.open("w") as stream:
        os.chmod(temporary, 0o600)
        json.dump(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def recover(spec: dict, journal: Path) -> None:
    (journal.parent / "capture/hub-postgresql.sql.gz").unlink(missing_ok=True)
    if not journal.exists():
        return
    state = json.loads(journal.read_text())
    allowed = set(spec["writers"])
    if not set(state["active"]).issubset(allowed):
        raise ValueError(
            "Invalid hub backup recovery journal; retain for operator review"
        )
    # Declarative unit conditions prevent restarts while the marker exists.
    (journal.parent / "quiescing").unlink(missing_ok=True)
    # Keep failed restarts in the journal for ExecStopPost/operator recovery.
    for unit in list(state["active"]):
        run("systemctl", "start", unit)
        state["active"].remove(unit)
        save(journal, state)
    journal.unlink()


def capture(spec: dict, journal: Path) -> None:
    exclusions = validate_paths(spec)
    if journal.exists():
        raise ValueError(
            "Interrupted hub backup requires recovery before another capture"
        )
    state = {"active": []}
    save(journal, state)
    try:
        (journal.parent / "quiescing").touch(mode=0o600)
        for unit in spec["writers"]:
            properties = dict(
                line.split("=", 1)
                for line in run(
                    "systemctl",
                    "show",
                    unit,
                    "--property=LoadState,ActiveState,UnitFileState",
                ).splitlines()
            )
            if properties.get("LoadState") not in {"loaded", "masked"}:
                raise ValueError("A declared backup writer is unavailable")
            if properties.get("ActiveState") == "failed":
                raise ValueError(
                    "A declared backup writer failed; inspect before capture"
                )
            if properties.get("ActiveState") != "inactive":
                state["active"].append(unit)
        save(journal, state)
        if spec["writers"]:
            run("systemctl", "stop", *spec["writers"])
        for unit in spec["writers"]:
            if (
                run("systemctl", "show", unit, "--property=ActiveState", "--value")
                != "inactive"
            ):
                raise ValueError("A hub writer is still active; no backup published")
            if unit in state["active"] and unit.endswith(".service"):
                if (
                    run("systemctl", "show", unit, "--property=Result", "--value")
                    != "success"
                ):
                    raise ValueError(
                        "A hub writer did not stop cleanly; no backup published"
                    )
        validate_paths(spec)
        # Fresh dump and media copy happen while the same writer set is stopped.
        run(*spec["capture_command"], json.dumps(exclusions), timeout=None)
    finally:
        recover(spec, journal)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("action", choices=["capture", "recover"])
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    journal = Path(spec["journal"])
    try:
        (capture if args.action == "capture" else recover)(spec, journal)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(
            1,
            f"Hub backup failed ({type(error).__name__}); inspect retained recovery state.\n",
        )


if __name__ == "__main__":
    main()
