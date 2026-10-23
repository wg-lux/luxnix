"""Create once, recover missing copies, and never replace established identity salts.

Center enrollment adds the authoritative center salt as a new active generation and
keeps an established machine salt as a retiring reader; no salt file is rewritten.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import fcntl
import grp
import hashlib
import os
from pathlib import Path
import pwd
import re
import runpy
import secrets
import stat
import sys
import subprocess
import yaml

ACTIVE = "lx_annotate_identity_active"
LEGACY = "lx_annotate_identity_legacy_default"
MANIFEST = "lx_annotate_identity_keyring.yml"
CENTER_PREFIX = "lx_annotate_identity_center_"
# Vault creates each center salt once with compare-and-set; rotation is not supported.
CENTER_GENERATION = 1
CENTER_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


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


def fingerprint_line(value: bytes) -> bytes:
    return hashlib.sha256(value).hexdigest().encode("ascii") + b"\n"


def machine_manifest(secret_dir: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "active": str(secret_dir / ACTIVE),
        "retiring": [str(secret_dir / LEGACY)],
        "allow_legacy_default_salt": True,
    }


def center_manifest(
    secret_dir: Path, center_id: str, history: bool
) -> dict[str, object]:
    """Keep the machine generation as a retiring reader for historical hashes."""
    return {
        "schema_version": 1,
        "active": str(secret_dir / f"{CENTER_PREFIX}{center_id}"),
        "retiring": [str(secret_dir / ACTIVE)] * history + [str(secret_dir / LEGACY)],
        "allow_legacy_default_salt": True,
        "center_id": center_id,
        "generation": CENTER_GENERATION,
    }


def publish_or_secure(
    fd: int, name: str, existing: bytes | None, content: bytes, uid: int, gid: int
):
    if existing is None:
        publish(fd, name, content, uid, gid, 0o600)
    else:
        os.chown(name, uid, gid, dir_fd=fd, follow_symlinks=False)
        os.chmod(name, 0o600, dir_fd=fd, follow_symlinks=False)


def provision(
    secret_dir: Path,
    recovery_dir: Path,
    replica_dir: Path,
    uid: int,
    gid: int,
    source_salt: Path | None = None,
    allow_initial_enrollment: bool = False,
    center_id: str | None = None,
):
    if source_salt is not None and center_id is None:
        raise ValueError("Center salt source and center must be supplied together")
    if center_id is not None:
        if source_salt is None:
            raise ValueError("Center salt source and center must be supplied together")
        if not CENTER_KEY.fullmatch(center_id):
            raise ValueError("Invalid center key for identity enrollment")
        return provision_center_salt(
            secret_dir, recovery_dir, replica_dir, uid, gid, source_salt, center_id
        )
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
        expected = machine_manifest(secret_dir)
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
        fingerprint = fingerprint_line(value)
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
            publish_or_secure(deployed, name, existing, content, uid, gid)


def provision_center_salt(
    secret_dir: Path,
    recovery_dir: Path,
    replica_dir: Path,
    uid: int,
    gid: int,
    source_salt: Path,
    center_id: str,
):
    """Enroll the Vault center salt as active; demote, never replace, a machine salt.

    The only file ever replaced is the keyring manifest, and only from the exact
    machine-only manifest to the center manifest after every generation and both
    recovery copies of each are durable.
    """
    if not source_salt.is_absolute():
        raise ValueError("Authoritative salt source must be absolute")
    center_name = f"{CENTER_PREFIX}{center_id}"
    center_backup = f"center-{center_id}.salt"
    center_receipt = f"center-{center_id}.enrolled"
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
        root = {os.geteuid()}
        stores = (primary, replica)

        with directory(source_salt.parent) as source_dir:
            source = read(source_dir, source_salt.name, owners)
        if source is None:
            raise ValueError("Center salt is unavailable; refusing local generation")
        center = salt_line(source)

        active = read(deployed, ACTIVE, owners)
        legacy = read(deployed, LEGACY, owners)
        manifest = read(deployed, MANIFEST, owners)
        if legacy is not None and legacy.rstrip(b"\r\n") != b"default_salt":
            raise ValueError("Established retiring salt differs; refusing replacement")
        backups = [read(fd, "active.salt", root) for fd in stores]
        receipts = [read(fd, "enrolled", root) for fd in stores]
        machine_values = {
            salt_line(raw) for raw in [active, *backups] if raw is not None
        }
        if len(machine_values) > 1:
            raise ValueError("Salt copies disagree; all copies preserved for recovery")
        machine = machine_values.pop() if machine_values else None

        deployed_center = read(deployed, center_name, owners)
        center_backups = [read(fd, center_backup, root) for fd in stores]
        center_receipts = [read(fd, center_receipt, root) for fd in stores]
        if any(
            salt_line(raw) != center
            for raw in [deployed_center, *center_backups]
            if raw is not None
        ):
            raise ValueError(
                "Center salt copies differ from the Vault source; all copies preserved"
            )
        center_fingerprint = fingerprint_line(center)
        if any(r is not None and r != center_fingerprint for r in center_receipts):
            raise ValueError("Center salt does not match its enrollment receipt")

        history = machine is not None and machine != center
        expected = center_manifest(secret_dir, center_id, history)
        established = yaml.safe_load(manifest) if manifest is not None else None
        previous_machine = machine_manifest(secret_dir)
        if machine is None and (
            any(receipt is not None for receipt in receipts)
            or established == previous_machine
            or established == center_manifest(secret_dir, center_id, True)
        ):
            raise ValueError(
                "Previously enrolled salt is missing; restore backup, never regenerate"
            )
        if established is not None and established not in (expected, previous_machine):
            raise ValueError(
                "Established manifest differs; refusing to replace its generations"
            )

        # Make the machine generation durable first: it stays the historical reader.
        if machine is not None:
            fingerprint = fingerprint_line(machine)
            if any(r is not None and r != fingerprint for r in receipts):
                raise ValueError(
                    "Salt does not match enrollment receipt; refusing replacement"
                )
            for fd, backup, receipt in zip(stores, backups, receipts):
                if backup is None:
                    publish(
                        fd,
                        "active.salt",
                        machine + b"\n",
                        os.geteuid(),
                        os.getegid(),
                        0o400,
                    )
                if receipt is None:
                    publish(
                        fd, "enrolled", fingerprint, os.geteuid(), os.getegid(), 0o400
                    )
            publish_or_secure(deployed, ACTIVE, active, machine + b"\n", uid, gid)
        for fd, backup, receipt in zip(stores, center_backups, center_receipts):
            if backup is None:
                publish(
                    fd, center_backup, center + b"\n", os.geteuid(), os.getegid(), 0o400
                )
            if receipt is None:
                publish(
                    fd,
                    center_receipt,
                    center_fingerprint,
                    os.geteuid(),
                    os.getegid(),
                    0o400,
                )
        publish_or_secure(
            deployed, center_name, deployed_center, center + b"\n", uid, gid
        )
        publish_or_secure(deployed, LEGACY, legacy, b"default_salt\n", uid, gid)

        content = yaml.safe_dump(expected).encode("utf-8")
        if established == expected or manifest is None:
            publish_or_secure(deployed, MANIFEST, manifest, content, uid, gid)
        else:
            # Atomic switch of new writes to the center generation.
            replace_private(deployed, MANIFEST, content, uid, gid)


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
    parser.add_argument(
        "--source-salt",
        type=Path,
        help="Private Vault-managed center salt file; requires --center-id.",
    )
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
        if args.source_bundle is None:
            if bool(args.source_salt) != bool(args.center_id):
                raise ValueError(
                    "Center salt source and center must be supplied together"
                )
            for path in (args.recovery_dir, args.replica_dir):
                encrypted_storage(path)
            encrypted_storage(args.secret_dir, allow_runtime=True)
            provision(
                args.secret_dir,
                args.recovery_dir,
                args.replica_dir,
                pwd.getpwnam(args.user).pw_uid,
                grp.getgrnam(args.group).gr_gid,
                source_salt=args.source_salt,
                allow_initial_enrollment=args.allow_create,
                center_id=args.center_id,
            )
            print("Identity salts verified with two durable recovery copies.")
            return 0
        if not args.center_id:
            raise ValueError("Source bundle and center must be supplied together")
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
