"""Dedicated age recovery identities and independently decryptable custody.

Explicit prepare creates missing native age identities only. Verify always performs
real challenge decryption. Export preserves the original vault record and publishes
an independently encrypted copy; no login identity, host or volume is changed.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import secrets
import stat
import subprocess
import time

from lx_administration.secret_storage import encrypted_storage, filesystem_devices
from lx_administration.storage.cutover import atomic_json


class CustodyError(ValueError):
    pass


def run(args, *, data=None):
    result = subprocess.run(
        args, input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60
    )
    if result.returncode:
        raise CustodyError(
            "Recovery cryptographic verification failed; existing material was retained"
        )
    return result.stdout


def private(path: Path, *, exists=True):
    if not path.is_absolute() or path.resolve() != path:
        raise CustodyError("Recovery paths must be absolute without symbolic links")
    encrypted_storage(path)
    parent = path.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or parent.st_mode & 0o077
    ):
        raise CustodyError(
            "Recovery parent must be a private directory owned by the operator"
        )
    if exists:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            raise CustodyError(
                "Recovery material must be a private regular file owned by the operator"
            )


def loop_backing_file(device: str) -> Path:
    try:
        name = Path(device).name
        backing = Path(f"/sys/block/{name}/loop/backing_file").read_text().strip()
    except OSError as error:
        raise CustodyError("Unable to identify a loop device's backing file") from error
    return Path(backing)


def storage_disks(path: Path) -> set[str]:
    current = path if path.exists() else path.parent
    mount = json.loads(
        run(
            [
                "findmnt",
                "--json",
                "--target",
                str(current),
                "--output",
                "SOURCE,FSTYPE,UUID",
            ]
        )
    )["filesystems"]
    if len(mount) != 1:
        raise CustodyError("Ambiguous recovery storage")
    fs = mount[0]
    sources = filesystem_devices(fs)
    disks = set()

    def visit(nodes):
        for node in nodes:
            if node.get("type") == "disk":
                disks.add(os.path.realpath(node["name"]))
            elif node.get("type") == "loop":
                # A file-backed volume lives on whatever disk holds that file.
                backing = loop_backing_file(node["name"])
                if not backing.is_file():
                    raise CustodyError("A loop device's backing file is missing")
                disks.update(storage_disks(backing))
            visit(node.get("children", []))

    for source in sources:
        tree = json.loads(
            run(
                [
                    "lsblk",
                    "--json",
                    "--paths",
                    "--inverse",
                    "--output",
                    "NAME,TYPE",
                    source,
                ]
            )
        )
        visit(tree["blockdevices"])
    if not disks:
        raise CustodyError("Recovery storage must resolve to physical disks")
    return disks


def independent(first: Path, second: Path):
    if storage_disks(first) & storage_disks(second):
        raise CustodyError(
            "Custodian storage shares a physical disk with the controller copy; "
            "select independent encrypted media"
        )


def recipient(identity: Path) -> str:
    private(identity)
    if identity.stat().st_size > 8192:
        raise CustodyError("Recovery identity is unexpectedly large")
    lines = [
        line
        for line in identity.read_text().splitlines()
        if line and not line.startswith("#")
    ]
    if len(lines) != 1 or not lines[0].startswith("AGE-SECRET-KEY-1"):
        raise CustodyError(
            "New backups require a dedicated native age identity; "
            "SSH login keys remain legacy-decryption only"
        )
    value = run(["age-keygen", "-y", str(identity)]).decode().strip()
    if not re.fullmatch(r"age1[0-9a-z]{58}", value):
        raise CustodyError("Invalid native age recipient")
    return value


def create_identity(path: Path):
    private(path, exists=False)
    if path.exists():
        recipient(path)
        return False
    # Serialize concurrent creation; never publish or overwrite a partial identity.
    lock_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if path.exists():
            recipient(path)
            return False
        value = run(["age-keygen"])
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        with os.fdopen(fd, "wb") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        del value
        os.fsync(lock_fd)
        recipient(path)
        return True
    finally:
        os.close(lock_fd)


def encrypt(data: bytes, recipients: list[str]) -> bytes:
    args = ["age"]
    for value in recipients:
        args += ["-r", value]
    return run(args, data=data)


def verify_pair(identity: Path, custodian: Path) -> dict:
    independent(identity, custodian)
    recipients = [recipient(identity), recipient(custodian)]
    if recipients[0] == recipients[1]:
        raise CustodyError("Custodian must hold a different recovery identity")
    challenge = secrets.token_bytes(64)
    envelope = encrypt(challenge, recipients)
    for key in (identity, custodian):
        if run(["age", "-d", "-i", str(key)], data=envelope) != challenge:
            raise CustodyError(
                "Independent identity cannot decrypt the recovery challenge"
            )
    return {
        "schema_version": 1,
        "recipients": recipients,
        "verified_at": time.time(),
        "independent_decryption_verified": True,
    }


def export_record(
    source: Path, vault_key: Path, custodian: Path, destination: Path
) -> dict:
    """Re-encrypt one actual vault record, never the admin-vault or login key."""
    from lx_administration.models.vault.secret import decrypt_secret

    for path in (source, vault_key, custodian):
        private(path)
    if source.stat().st_size > 1024 * 1024:
        raise CustodyError("Recovery record is unexpectedly large")
    private(destination, exists=destination.exists())
    independent(source, destination)
    independent(vault_key, custodian)
    value = decrypt_secret(source, vault_key)
    record = json.loads(value)
    if not isinstance(record, dict) or not all(
        record.get(k)
        for k in ("machine_id", "luks_uuid", "volume", "recovery_passphrase")
    ):
        raise CustodyError("Source is not an identity-bound LUKS recovery record")
    public = recipient(custodian)
    directory = os.open(
        destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    )
    try:
        fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not destination.exists():
            envelope = encrypt(value, [public])
            if run(["age", "-d", "-i", str(custodian)], data=envelope) != value:
                raise CustodyError(
                    "Custodian readback did not authenticate the existing record"
                )
            fd = os.open(
                destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400
            )
            with os.fdopen(fd, "wb") as output:
                output.write(envelope)
                output.flush()
                os.fsync(output.fileno())
            os.fsync(directory)
        if run(["age", "-d", "-i", str(custodian), str(destination)]) != value:
            raise CustodyError(
                "Existing independent envelope differs; never replace recovery material"
            )
        receipt = {
            "schema_version": 1,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "envelope_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "recipient": public,
            "machine_id": record["machine_id"],
            "luks_uuid": record["luks_uuid"],
            "volume": record["volume"],
            "verified_at": time.time(),
            "independent_decryption_verified": True,
        }
        atomic_json(
            destination.with_suffix(destination.suffix + ".receipt.json"), receipt
        )
        return receipt
    finally:
        os.close(directory)


def configure_vault(vault: Path, custodian: Path, directory: Path):
    """Install explicit operator custody selection, without replacing an old policy."""
    if not directory.is_dir() or not vault.is_dir():
        raise CustodyError(
            "Select existing encrypted vault and independent export directories"
        )
    independent(vault, directory)
    independent(vault, custodian)
    recipient(custodian)
    root = vault / "storage-recovery"
    encrypted_storage(root)
    root.mkdir(mode=0o700, exist_ok=True)
    path = root / "custody.json"
    private(path, exists=path.exists())
    policy = {
        "schema_version": 1,
        "custodian_identity": str(custodian),
        "export_directory": str(directory),
        "recipient": recipient(custodian),
    }
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if path.exists():
            if json.loads(path.read_text()) != policy:
                raise CustodyError(
                    "Existing custody selection differs; "
                    "review old recovery retention before changing it"
                )
        else:
            atomic_json(path, policy)
    finally:
        os.close(fd)


def export_configured(vault: Path, vault_key: Path, source: Path):
    policy_path = vault / "storage-recovery/custody.json"
    private(policy_path)
    policy = json.loads(policy_path.read_text())
    if (
        set(policy)
        != {"schema_version", "custodian_identity", "export_directory", "recipient"}
        or policy["schema_version"] != 1
    ):
        raise CustodyError("Invalid recovery custody selection")
    custodian, directory = (
        Path(policy["custodian_identity"]),
        Path(policy["export_directory"]),
    )
    if recipient(custodian) != policy["recipient"]:
        raise CustodyError("The selected custodian identity changed")
    # UUID and machine directory names come from the authenticated vault record.
    from lx_administration.models.vault.secret import decrypt_secret

    record = json.loads(decrypt_secret(source, vault_key))
    machine, identifier = record["machine_id"], record["luks_uuid"]
    if not re.fullmatch("[0-9a-f]{32}", machine) or not re.fullmatch(
        "[0-9a-f-]{36}", identifier
    ):
        raise CustodyError("Invalid recovery record identity")
    independent(vault, directory)
    parent = directory / machine
    encrypted_storage(parent)
    parent.mkdir(mode=0o700, exist_ok=True)
    return export_record(source, vault_key, custodian, parent / (identifier + ".age"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("prepare", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--identity", required=True, type=Path)
        command.add_argument("--custodian-identity", required=True, type=Path)
        if name == "prepare":
            command.add_argument("--vault-dir", type=Path)
            command.add_argument("--export-directory", type=Path)
    command = sub.add_parser("export-vault-record")
    command.add_argument("--source", required=True, type=Path)
    command.add_argument("--vault-key", required=True, type=Path)
    command.add_argument("--custodian-identity", required=True, type=Path)
    command.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        if args.action == "export-vault-record":
            result = export_record(
                args.source, args.vault_key, args.custodian_identity, args.destination
            )
        else:
            independent(args.identity, args.custodian_identity)
            if args.action == "prepare":
                create_identity(args.identity)
                create_identity(args.custodian_identity)
            result = verify_pair(args.identity, args.custodian_identity)
            if args.action == "prepare" and (args.vault_dir or args.export_directory):
                if not args.vault_dir or not args.export_directory:
                    raise CustodyError(
                        "Select both vault and independent export directories"
                    )
                configure_vault(
                    args.vault_dir, args.custodian_identity, args.export_directory
                )
        print(json.dumps(result, sort_keys=True))
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError):
        parser.exit(
            1,
            "Recovery custody verification did not complete. "
            "Existing keys and archives were retained; "
            "check the selected encrypted media and identity files.\n",
        )


if __name__ == "__main__":
    main()
