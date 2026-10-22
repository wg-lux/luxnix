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
import runpy
import secrets
import stat
import sys
import subprocess
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

def generate_identity_salt() -> bytes:
    return secrets.token_hex(32).encode("ascii")

def provision(
    secret_dir: Path,
    recovery_dir: Path,
    replica_dir: Path,
    uid: int,
    gid: int,
    source_salt: Path | None = None,
    allow_initial_enrollment: bool = False,
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
        expected: dict[str, str | int | bool | list[str]] = {
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
        if source_salt is not None:
            if not source_salt.is_absolute():
                raise ValueError("Authoritative salt source must be absolute")
            with directory(source_salt.parent) as source_dir:
                source = read(source_dir, source_salt.name, owners)
            if source is None:
                raise ValueError(
                    "Center salt is unavailable; refusing local generation"
                )
            values.add(salt_line(source))
        if len(values) > 1:
            raise ValueError("Salt copies disagree; all copies preserved for recovery")
        if not values and any(
            raw is not None for raw in [manifest, legacy, *receipts]
        ):
            raise ValueError(
                "Previously enrolled salt is missing; restore backup, never regenerate"
            )

        if not values:
            if not allow_initial_enrollment:
                raise ValueError(
                    "Initial identity enrollment must be explicitly requested"
                )
            values.add(generate_identity_salt())
        if not values:
            raise ValueError(
                "Authoritative center salt required; local generation is prohibited"
            )
        value = values.pop()
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

encrypted_storage = runpy.run_path(
    str(Path(__file__).with_name("verify-secret-storage.py"))
)["encrypted_storage"]


def replace_private(fd: int, name: str, content: bytes, uid: int, gid: int) -> None:
    temporary = f".pending-{secrets.token_hex(12)}"
    publish(fd, temporary, content, uid, gid, 0o600)
    try:
        os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass


def provision_center(
    secret_dir: Path,
    recovery_dir: Path,
    replica_dir: Path,
    uid: int,
    gid: int,
    source_bundle: Path,
    center_id: str,
) -> None:
    """Reject retired central enrollment before reading or mutating any files."""
    raise ValueError("Central identity salt provisioning is disabled")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("secret-dir", "recovery-dir", "replica-dir"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--source-bundle", type=Path)
    parser.add_argument("--center-id")
    parser.add_argument(
        "--allow-create",
        action="store_true",
        help=(
            "Permit explicit first enrollment when no existing identity "
            "material or enrollment evidence is present."
        ),
    )
    args = parser.parse_args()
    try:
        if bool(args.source_bundle) != bool(args.center_id):
            raise ValueError("Source bundle and center must be supplied together")
        if args.source_bundle is None:
            for path in (args.recovery_dir, args.replica_dir):
                encrypted_storage(path)
            encrypted_storage(args.secret_dir, allow_runtime=True)
            provision(
                args.secret_dir,
                args.recovery_dir,
                args.replica_dir,
                pwd.getpwnam(args.user).pw_uid,
                grp.getgrnam(args.group).gr_gid,
                allow_initial_enrollment=args.allow_create
            )
            return 0
        provision_center(
            args.secret_dir,
            args.recovery_dir,
            args.replica_dir,
            pwd.getpwnam(args.user).pw_uid,
            grp.getgrnam(args.group).gr_gid,
            args.source_bundle,
            args.center_id,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        yaml.YAMLError,
    ):
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
