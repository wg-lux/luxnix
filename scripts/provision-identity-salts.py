"""Keep LX-Annotate's identity salts working without anyone having to decide anything.

Center enrollment adds the authoritative center salt as a new active generation and
keeps an established machine salt as a retiring reader; no salt file is rewritten.
Unusable files are set aside, never deleted. Salts are still never written outside
encrypted storage, which is the one thing that stops this.
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


def set_aside(fd: int, name: str) -> None:
    """Keep what cannot be used under a new name; nothing here is ever deleted."""
    os.rename(
        name,
        f"{name}.superseded-{secrets.token_hex(6)}",
        src_dir_fd=fd,
        dst_dir_fd=fd,
    )
    os.fsync(fd)
    print(f"Identity salts: set aside unusable {name}", file=sys.stderr)


def usable(fd: int, name: str, owners: set[int], parse=salt_line):
    try:
        raw = read(fd, name, owners)
        return None if raw is None else parse(raw)
    except (OSError, ValueError, yaml.YAMLError):
        set_aside(fd, name)
        return None


def exists_in(fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def agree(copies: list, receipts: list) -> bytes | None:
    """A copy matching a receipt wins, then the first copy; others are set aside."""
    values = [value for _, _, value in copies if value is not None]
    if not values:
        chosen = None
    else:
        receipted = {raw for _, _, raw in receipts if raw is not None}
        chosen = next(
            (value for value in values if fingerprint_line(value) in receipted),
            values[0],
        )
    for fd, name, value in copies:
        if value is not None and value != chosen:
            set_aside(fd, name)
    for fd, name, raw in receipts:
        if raw is not None and (chosen is None or raw != fingerprint_line(chosen)):
            set_aside(fd, name)
    return chosen


def settle_generation(
    deployed: int,
    stores: tuple[int, int],
    names: tuple[str, str, str],
    ids: tuple[int, int],
    owners: set[int],
    fallback=None,
) -> bytes | None:
    """Make one generation whole from any surviving copy, or from the fallback."""
    active, backup, receipt = names
    root = {os.geteuid()}
    copies = [(deployed, active, usable(deployed, active, owners))] + [
        (fd, backup, usable(fd, backup, root)) for fd in stores
    ]
    receipts = [(fd, receipt, usable(fd, receipt, root, bytes)) for fd in stores]
    value = agree(copies, receipts)
    if value is None and fallback is not None:
        value = fallback()
    if value is None:
        return None
    # Persist both recovery copies and receipts before publishing the active salt.
    for fd in stores:
        if not exists_in(fd, backup):
            publish(fd, backup, value + b"\n", os.geteuid(), os.getegid(), 0o400)
        if not exists_in(fd, receipt):
            publish(
                fd, receipt, fingerprint_line(value), os.geteuid(), os.getegid(), 0o400
            )
    place(deployed, active, value + b"\n", *ids)
    return value


def place(fd: int, name: str, content: bytes, uid: int, gid: int) -> None:
    publish_or_secure(fd, name, b"" if exists_in(fd, name) else None, content, uid, gid)


def read_source(source_salt: Path | None, owners: set[int]) -> bytes | None:
    """Vault may be unreachable; that only means this salt is not available yet."""
    if source_salt is None:
        return None
    try:
        with directory(source_salt.parent) as source_dir:
            raw = read(source_dir, source_salt.name, owners)
        return None if raw is None else salt_line(raw)
    except (OSError, ValueError):
        print("Identity salts: center salt is unavailable for now", file=sys.stderr)
        return None


def parse_manifest(raw: bytes) -> dict:
    manifest = yaml.safe_load(raw)
    if not isinstance(manifest, dict):
        raise ValueError("Keyring manifest is not a mapping")
    return manifest


def parse_legacy(raw: bytes) -> bytes:
    if raw.rstrip(b"\r\n") != b"default_salt":
        raise ValueError("Unexpected retiring salt")
    return raw


def provision(
    secret_dir: Path,
    recovery_dir: Path,
    replica_dir: Path,
    uid: int,
    gid: int,
    source_salt: Path | None = None,
    center_id: str | None = None,
):
    """Always leave a working keyring, and never make anyone decide anything.

    An active center salt is kept for good: Vault cannot replace it and the inventory
    cannot leave it. A host with no usable salt, including one that only ever had
    default_salt, gets a new random salt; default_salt stays a retiring reader. Without
    a center salt yet, the host uses its own until Vault can deliver one. Anything
    unusable is set aside rather than deleted, and values are never logged.
    """
    if (source_salt is None) != (center_id is None):
        raise ValueError("Center salt source and center must be supplied together")
    if center_id is not None and not CENTER_KEY.fullmatch(center_id):
        raise ValueError("Invalid center key for identity enrollment")
    if source_salt is not None and not source_salt.is_absolute():
        raise ValueError("Authoritative salt source must be absolute")
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
        stores = (primary, replica)
        ids = (uid, gid)
        manifest = usable(deployed, MANIFEST, owners, parse_manifest)
        established = (manifest or {}).get("center_id")
        if not (isinstance(established, str) and CENTER_KEY.fullmatch(established)):
            established = None
        center = established or center_id
        source = read_source(source_salt, owners) if center == center_id else None

        center_value = None
        if center is not None:
            center_value = settle_generation(
                deployed,
                stores,
                (
                    f"{CENTER_PREFIX}{center}",
                    f"center-{center}.salt",
                    f"center-{center}.enrolled",
                ),
                ids,
                owners,
                fallback=lambda: source,
            )
        # Only a host with no center salt needs a new generation of its own.
        machine = settle_generation(
            deployed,
            stores,
            (ACTIVE, "active.salt", "enrolled"),
            ids,
            owners,
            fallback=None if center_value is not None else generate_identity_salt,
        )
        if usable(deployed, LEGACY, owners, parse_legacy) is None:
            publish(deployed, LEGACY, b"default_salt\n", uid, gid, 0o600)
        else:
            place(deployed, LEGACY, b"default_salt\n", *ids)

        expected = (
            center_manifest(
                secret_dir, center, machine is not None and machine != center_value
            )
            if center_value is not None
            else machine_manifest(secret_dir)
        )
        content = yaml.safe_dump(expected).encode("utf-8")
        if manifest is None:
            publish(deployed, MANIFEST, content, uid, gid, 0o600)
        elif manifest == expected:
            place(deployed, MANIFEST, content, *ids)
        else:
            # Atomic switch of new writes, only after every generation is durable.
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
            "Check that the salt directories are on mounted encrypted storage.",
            file=sys.stderr,
        )
        return 1
    print("Identity salts verified with two durable recovery copies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
