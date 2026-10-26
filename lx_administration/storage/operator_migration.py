"""Prepare operator-owned encrypted containers and migrate before writers start.

Never format an existing file, overwrite a populated destination, or remove a
source. The JSON contract contains paths only; passphrases never enter it.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys


class MigrationError(RuntimeError):
    pass


def run(*args, input=None):
    result = subprocess.run(args, input=input, capture_output=True, check=False)
    if result.returncode:
        # rsync and cryptsetup diagnostics can contain private filenames.
        raise MigrationError(f"{args[0]} failed (exit {result.returncode}); sources retained")
    return result.stdout


def plain_path(value):
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or path.resolve() != path:
        raise MigrationError("Storage paths must be absolute and contain no symlinks")
    return path


def atomic_json(path, value):
    temporary = path.with_suffix(".pending")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    run("sync", "-f", str(path.parent))


class Migration:
    def __init__(self, config, verifier):
        self.config = config
        self.verifier = verifier

    def unlock(self, name):
        volume = self.config["volumes"][name]
        container = plain_path(volume["container"])
        mapping = volume["device"].removeprefix("/dev/mapper/")
        if Path(volume["device"]).exists():
            status = run("cryptsetup", "status", mapping).decode()
            fields = dict(line.strip().split(":", 1) for line in status.splitlines() if ":" in line)
            if fields.get("loop", "").strip() != str(container):
                raise MigrationError("Open mapping has a different backing container")
            return
        self.verifier._require_protected_swap()
        new = not container.exists()
        if new:
            # Reserve enough for existing contents plus headroom. Never resize or
            # format existing files; an interrupted new allocation needs inspection.
            sources = [plain_path(path) for path, bind in self.config["binds"].items()
                       if bind["volume"] == name and Path(path).exists()]
            used = sum(int(run("du", "-sx", "--block-size=1", str(path)).split()[0]) for path in sources)
            size = max(volume["minimumSizeMiB"] * 1024**2, used * 2 + 256 * 1024**2)
            if shutil.disk_usage(container.parent).free < size + 256 * 1024**2:
                raise MigrationError("Insufficient space for encrypted copy and safety reserve")
            first = run("systemd-ask-password", "--timeout=0", f"New passphrase for {mapping}:")
            second = run("systemd-ask-password", "--timeout=0", f"Repeat passphrase for {mapping}:")
            if not first.rstrip(b"\n") or first != second:
                raise MigrationError("Passphrases are empty or do not match; nothing created")
            fd = os.open(container, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.posix_fallocate(fd, 0, size)
                os.fsync(fd)
            finally:
                os.close(fd)
            key = first.rstrip(b"\n")
            run("cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", "--key-file=-", str(container), input=key)
        else:
            if not container.is_file():
                raise MigrationError("Configured container is not a regular file")
            run("cryptsetup", "isLuks", str(container))
            key = run("systemd-ask-password", "--timeout=0", f"Unlock {mapping}:").rstrip(b"\n")
        run("cryptsetup", "open", "--type", "luks", "--key-file=-", str(container), mapping, input=key)
        del key
        if new:
            # Only the mapping just created from our exclusively created file.
            run("mkfs.ext4", "-q", volume["device"])

    def receipt(self, source, destination, root):
        directory = root / ".luxnix-migrations"
        if directory.exists():
            plain_path(str(directory))
            info = directory.stat()
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise MigrationError("Migration receipt directory must be root-owned mode 0700")
        else:
            directory.mkdir(mode=0o700)
        name = hashlib.sha256(f"{source}\0{destination}".encode()).hexdigest()
        return directory / (name + ".json")

    def identity(self, source, destination):
        uuid = run("findmnt", "-n", "-o", "UUID", "-T", str(destination)).decode().strip()
        if not uuid:
            raise MigrationError("Encrypted destination has no filesystem UUID")
        return {"source": str(source), "destination": str(destination),
                "inode": destination.stat().st_ino,
                "uuid": uuid}

    def copy(self, source, destination, excludes, dry=False):
        args = ["rsync", "-aHAXx", "--numeric-ids", "--checksum"]
        if not dry:
            args += ["--delete"]  # Only ever applied to our private staging copy.
        if dry:
            args += ["--dry-run", "--delete", "--itemize-changes", "--out-format=%i"]
        for path in excludes:
            args += ["--exclude=/" + path + "/***"]
        return run(*args, str(source) + "/", str(destination) + "/")

    def prepare(self):
        pending = []
        for value, bind in self.config["binds"].items():
            source = plain_path(value)
            root = plain_path(self.config["volumes"][bind["volume"]]["mountPoint"])
            if not os.path.ismount(root):
                raise MigrationError("Encrypted volume is not mounted")
            destination = plain_path(str(root / bind["directory"]))
            self.verifier.encrypted_storage(destination)
            receipt = self.receipt(source, destination, root)
            if receipt.exists():
                plain_path(str(receipt))
                if not destination.is_dir() or json.loads(receipt.read_text()) != self.identity(source, destination):
                    raise MigrationError("Migration receipt does not match its destination")
                continue
            if source.exists() and destination.exists() and os.path.samefile(source, destination):
                atomic_json(receipt, self.identity(source, destination))
                continue
            excludes = [str(Path(path).relative_to(source)) for path in self.config["binds"]
                        if Path(path).is_relative_to(source) and Path(path) != source]
            if source.exists():
                device = source.stat().st_dev
                for directory, children, _ in os.walk(source):
                    children[:] = [name for name in children if
                        str((Path(directory) / name).relative_to(source)) not in excludes]
                    if Path(directory).stat().st_dev != device:
                        raise MigrationError("Unconfigured nested filesystem; declare its bind before migration")
            pending.append((source, destination, receipt, excludes))
        if not pending:
            return
        # Normal startup orders all writers behind this service. Refuse a live
        # retrofit rather than copying a running PostgreSQL cluster or stopping
        # healthy services behind an operator's back.
        for name in self.config["writers"]:
            if int(run("systemctl", "show", "--value", "-p", "MainPID", name + ".service").strip() or b"0"):
                raise MigrationError("A storage writer is running; migration requires a stopped application")
        for source, destination, receipt, excludes in pending:
            if source.exists() and not source.is_dir():
                raise MigrationError("Migration source is not a directory")
            if destination.exists():
                # Adopt a prepared copy only after equality, never overwrite it.
                if not source.is_dir() or self.copy(source, destination, excludes, dry=True).strip():
                    raise MigrationError("Existing encrypted destination differs; refusing overwrite")
            else:
                stage = plain_path(str(destination) + ".luxnix-copy")
                plan = {"source": str(source), "destination": str(destination)}
                if stage.exists():
                    info = stage.stat()
                    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                        raise MigrationError("Untrusted staging directory")
                    if not (stage / "plan.json").is_file() or json.loads((stage / "plan.json").read_text()) != plan:
                        raise MigrationError("Staging copy belongs to another migration")
                else:
                    stage.mkdir(mode=0o700, parents=True)
                    atomic_json(stage / "plan.json", plan)
                payload = plain_path(str(stage / "data"))
                payload.mkdir(mode=0o700, exist_ok=True)
                if source.is_dir():
                    self.copy(source, payload, excludes)
                    if self.copy(source, payload, excludes, dry=True).strip():
                        raise MigrationError("Copy verification failed; sources retained")
                run("sync", "-f", str(payload))
                if destination.exists():
                    raise MigrationError("Destination appeared while copying")
                payload.rename(destination)
                (stage / "plan.json").unlink()
                stage.rmdir()
            atomic_json(receipt, self.identity(source, destination))


def prepare_accounts(accounts):
    for target, source in accounts.items():
        target, source = plain_path(target), plain_path(source)
        if target.exists():
            continue
        info = source.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) not in (0o400, 0o600):
            raise MigrationError("Boot account hash source must be a private root-owned regular file")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(source.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("action", choices=["unlock", "prepare", "accounts"])
    parser.add_argument("volume", nargs="?")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    spec = importlib.util.spec_from_file_location("storage_verifier", config["verifier"])
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    try:
        if os.geteuid() != 0:
            raise MigrationError("Run as root")
        os.umask(0o077)
        # /run is runtime-only; this lock contains no passphrase or secret data.
        Path("/run/lock").mkdir(mode=0o755, exist_ok=True)
        with open("/run/lock/luxnix-operator-migration", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            migration = Migration(config, verifier)
            if args.action == "unlock":
                migration.unlock(args.volume)
            elif args.action == "accounts":
                prepare_accounts(config["accounts"])
            else:
                migration.prepare()
    except (MigrationError, ValueError, OSError, KeyError) as exc:
        # No subprocess stderr or source contents are emitted.
        print(f"ERROR: encrypted storage preparation: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
