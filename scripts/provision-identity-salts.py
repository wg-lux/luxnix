"""Create once, recover missing copies, and never replace established identity salts."""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import fcntl
import grp
import hashlib
import os
from pathlib import Path
import pwd
import secrets
import stat
import sys

import yaml

ACTIVE = "lx_annotate_identity_active"
LEGACY = "lx_annotate_identity_legacy_default"
MANIFEST = "lx_annotate_identity_keyring.yml"


@contextmanager
def directory(path: Path, *, private: bool = False, group: int | None = None):
    """Traverse without following symlinks; only create the final directory."""
    if not path.is_absolute():
        raise ValueError("Salt directories must be absolute")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for index, part in enumerate(path.parts[1:]):
            if part == "..":
                raise ValueError("Salt directories must not contain parent traversal")
            created = False
            if index == len(path.parts) - 2:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                    created = True
                    os.fsync(fd)
                except FileExistsError:
                    pass
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
            if created and group is not None:
                os.fchown(fd, os.geteuid(), group)
                os.fchmod(fd, 0o750)
                os.fsync(fd)
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & (0o077 if private else 0o022):
            raise ValueError("Salt directory ownership or permissions are unsafe")
        yield fd
    finally:
        os.close(fd)


def read(fd: int, name: str, owners: set[int]) -> bytes | None:
    try:
        source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None
    with os.fdopen(source, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid not in owners
            or info.st_mode & 0o077
        ):
            raise ValueError("Salt files must be private regular files")
        value = stream.read(65537)
    if not value or len(value) > 65536:
        raise ValueError("Salt file is empty or oversized; refusing replacement")
    return value


def publish(fd: int, name: str, value: bytes, uid: int, gid: int, mode: int):
    """Durably publish a missing file without an overwrite window."""
    temporary = f".pending-{secrets.token_hex(12)}"
    target = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd)
    try:
        with os.fdopen(target, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fchown(stream.fileno(), uid, gid)
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
    finally:
        os.unlink(temporary, dir_fd=fd)
        os.fsync(fd)


def salt_line(raw: bytes) -> bytes:
    value = (
        raw.removesuffix(b"\r\n") if raw.endswith(b"\r\n") else raw.removesuffix(b"\n")
    )
    text = value.decode("utf-8")
    if (
        not text
        or text != text.strip()
        or "\n" in text
        or "\r" in text
        or text == "default_salt"
        or len(value) > 4096
    ):
        raise ValueError("Invalid active identity salt; refusing replacement")
    return value


def provision(
    secret_dir: Path, recovery_dir: Path, replica_dir: Path, uid: int, gid: int
):
    with ExitStack() as stack:
        primary = stack.enter_context(directory(recovery_dir, private=True))
        lock = os.open(
            ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=primary
        )
        stack.callback(os.close, lock)
        fcntl.flock(lock, fcntl.LOCK_EX)
        replica = stack.enter_context(directory(replica_dir, private=True))
        deployed = stack.enter_context(directory(secret_dir, group=gid))
        if (
            len(
                {
                    (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
                    for fd in (primary, replica, deployed)
                }
            )
            != 3
        ):
            raise ValueError("Salt recovery directories must be distinct")
        owners = {os.geteuid(), uid}
        active = read(deployed, ACTIVE, owners)
        legacy = read(deployed, LEGACY, owners)
        manifest = read(deployed, MANIFEST, owners)
        expected = {
            "schema_version": 1,
            "active": str(secret_dir / ACTIVE),
            "retiring": [str(secret_dir / LEGACY)],
            "allow_legacy_default_salt": True,
        }
        if manifest is not None and yaml.safe_load(manifest) != expected:
            raise ValueError(
                "Established manifest differs; refusing to replace its generations"
            )
        if legacy is not None and legacy.rstrip(b"\r\n") != b"default_salt":
            raise ValueError("Established retiring salt differs; refusing replacement")
        backups = [read(fd, "active.salt", {os.geteuid()}) for fd in (primary, replica)]
        receipts = [read(fd, "enrolled", {os.geteuid()}) for fd in (primary, replica)]
        values = {salt_line(raw) for raw in [active, *backups] if raw is not None}
        if len(values) > 1:
            raise ValueError("Salt copies disagree; all copies preserved for recovery")
        if not values and any(raw is not None for raw in [manifest, legacy, *receipts]):
            raise ValueError(
                "Previously enrolled salt is missing; restore backup, never regenerate"
            )
        value = values.pop() if values else secrets.token_hex(32).encode("ascii")
        fingerprint = hashlib.sha256(value).hexdigest().encode("ascii") + b"\n"
        if any(receipt is not None and receipt != fingerprint for receipt in receipts):
            raise ValueError(
                "Salt does not match enrollment receipt; refusing replacement"
            )
        # Persist both recovery copies and receipts before publishing the active salt.
        for fd, backup, receipt in zip((primary, replica), backups, receipts):
            if backup is None:
                publish(
                    fd, "active.salt", value + b"\n", os.geteuid(), os.getegid(), 0o400
                )
            if receipt is None:
                publish(fd, "enrolled", fingerprint, os.geteuid(), os.getegid(), 0o400)
        for name, existing, content in (
            (ACTIVE, active, value + b"\n"),
            (LEGACY, legacy, b"default_salt\n"),
            (MANIFEST, manifest, yaml.safe_dump(expected).encode("utf-8")),
        ):
            if existing is None:
                publish(deployed, name, content, uid, gid, 0o600)
            else:
                os.chown(name, uid, gid, dir_fd=deployed, follow_symlinks=False)
                os.chmod(name, 0o600, dir_fd=deployed, follow_symlinks=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("secret-dir", "recovery-dir", "replica-dir"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--group", required=True)
    args = parser.parse_args()
    try:
        provision(
            args.secret_dir,
            args.recovery_dir,
            args.replica_dir,
            pwd.getpwnam(args.user).pw_uid,
            grp.getgrnam(args.group).gr_gid,
        )
    except (OSError, ValueError, KeyError, yaml.YAMLError):
        # Never render parser exceptions or file contents into service logs.
        print(
            "Identity salt provisioning failed; existing files preserved. "
            "Check private file metadata, copy agreement and enrollment receipts.",
            file=sys.stderr,
        )
        return 1
    print("Identity salts verified with two durable recovery copies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
