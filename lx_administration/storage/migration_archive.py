"""Standalone authenticated archive transport for controller or host-local snapshots."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shlex
import socket
import stat
import subprocess
import time

if __package__:
    from .migration_policy import validate_snapshot, snapshot_sources
else:
    from migration_policy import validate_snapshot, snapshot_sources


def private_directory(path):
    info = path.lstat()
    if (
        path.resolve() != path
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError(
            "Backup directory must be an owned private directory without symlinks"
        )


def private_open(path, flags=os.O_RDONLY):
    """Open metadata without following links, then validate the opened inode."""
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
        ):
            raise ValueError(
                "Backup metadata must be an owned private regular file "
                "without hard links"
            )
        return os.fdopen(fd, "r+" if flags & os.O_RDWR else "r")
    except BaseException:
        os.close(fd)
        raise


def read_receipt(path):
    try:
        with private_open(path) as stream:
            return json.load(stream)
    except FileNotFoundError:
        return None


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def plan_binding(plan, recipients):
    """Bind every observation, snapshot identity and selected recovery recipient."""
    recipients = sorted(set(recipients))
    digest = hashlib.sha256(
        json.dumps(
            {"plan": plan, "recipients": recipients},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {
        "host": plan["host"],
        "snapshot_id": plan["identifier"],
        "source_plan_sha256": digest,
        "recipients": recipients,
    }


def bind_receipt(root, plan, recipients, initial=None):
    binding = plan_binding(plan, recipients)
    receipt_path = root / "receipt.json"
    receipt = read_receipt(receipt_path)
    if receipt is not None:
        provenance = dict(initial or {})
        if "custody" in provenance:
            provenance["custody"] = {
                k: v for k, v in provenance["custody"].items() if k != "verified_at"
            }
        actual = dict(receipt)
        if "custody" in actual:
            actual["custody"] = {
                k: v for k, v in actual["custody"].items() if k != "verified_at"
            }
        if (
            any(actual.get(key) != value for key, value in provenance.items())
            or any(receipt.get(key) != value for key, value in binding.items())
            or not set(receipt.get("components", {})).issubset(
                i["name"] for i in plan["snapshots"]
            )
            or any(
                item.get("source_plan_sha256") != binding["source_plan_sha256"]
                for item in receipt.get("components", {}).values()
            )
        ):
            raise ValueError(
                "Backup receipt differs from the complete source plan or recipients; "
                "operator review required"
            )
    saved_plan = read_receipt(root / "source-plan.json")
    if saved_plan is not None and saved_plan != plan:
        raise ValueError("Saved source plan differs; refusing replacement")
    if receipt is None:
        receipt = dict(
            initial or {},
            **binding,
            components={},
            complete=False,
            application_restore_tested=False,
        )
        save_receipt(receipt_path, receipt)
    if saved_plan is None:
        save_receipt(root / "source-plan.json", plan)
    return receipt


def archive_result(target, digest, count, authenticated):
    return {
        "compressed_bytes": count,
        "sha256_compressed_stream": digest,
        "authenticated": authenticated,
        "artifact": target.name,
        "application_restore_tested": False,
    }


def recover_transfer(target, recipients, identities, binding):
    """Recover a fully transferred archive after publication/receipt interruption."""
    metadata = read_receipt(target.with_suffix(target.suffix + ".json"))
    if metadata is None:
        return None
    if metadata.get("binding") != binding or metadata.get("recipients") != sorted(
        set(recipients)
    ):
        raise ValueError(
            "Archive recovery metadata differs from source plan or recipients"
        )
    result = dict(metadata["result"])
    if result.get("source_plan_sha256") != binding:
        raise ValueError("Archive component differs from the source plan binding")
    result["authenticated"] = identities is not None
    allowed = {target.name, target.name + ".unverified"}
    if result["artifact"] not in allowed or (
        identities is not None and result["artifact"] != target.name
    ):
        raise ValueError("Unexpected recovery artifact")
    expected = target.parent / result["artifact"]
    partial = target.with_suffix(target.suffix + ".partial")
    artifact = expected if expected.exists() else partial
    # Never upgrade unauthenticated host-local output from metadata alone.
    if identities is not None:
        for key in identities if isinstance(identities, list) else [identities]:
            verify_archive(artifact, key, result["sha256_compressed_stream"])
    elif not artifact.is_file() or artifact.is_symlink():
        raise ValueError("Missing or unsafe encrypted recovery artifact")
    if not expected.exists():
        os.link(artifact, expected, follow_symlinks=False)
        sync_directory(expected.parent)
    if partial.exists():
        if not os.path.samefile(partial, expected):
            raise ValueError("Conflicting partial archive; operator review required")
        partial.unlink()
        sync_directory(expected.parent)
    return result


def verify_archive(path, identity, digest, *, pass_fds=()):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        os.close(fd)
        raise ValueError("Unsafe archive file")
    try:
        process = subprocess.Popen(
            ["age", "-d", "-i", str(identity), f"/proc/self/fd/{fd}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            pass_fds=(*pass_fds, fd),
        )
    finally:
        os.close(fd)
    actual = hashlib.sha256()
    try:
        while chunk := process.stdout.read(4 * 1024 * 1024):
            actual.update(chunk)
        if process.wait() != 0 or actual.hexdigest() != digest:
            raise ValueError(
                "Encrypted archive authentication or stream checksum failed"
            )
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait()


def recover_existing(remote, command, target, recipients, identities, binding):
    """Explicitly adopt an orphan only after matching the current source stream."""
    artifact = (
        target if target.exists() else target.with_suffix(target.suffix + ".unverified")
    )
    if not artifact.exists() or not identities:
        raise ValueError(
            "Orphan recovery requires an existing archive and independent decryption"
        )
    source = (
        remote.open_stream(command, privileged=True)
        if remote
        else subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    )
    digest, count = hashlib.sha256(), 0
    try:
        source.stdin.close()
        while chunk := source.stdout.read(4 * 1024 * 1024):
            digest.update(chunk)
            count += len(chunk)
        if source.wait():
            raise ValueError("Cannot independently read current snapshot stream")
        for key in identities:
            if isinstance(key, tuple):
                verify_archive(artifact, key[0], digest.hexdigest(), pass_fds=(key[1],))
            else:
                verify_archive(artifact, key, digest.hexdigest())
    finally:
        source.stdout.close()
        if source.poll() is None:
            source.kill()
            source.wait()
    result = archive_result(artifact, digest.hexdigest(), count, False)
    result["source_plan_sha256"] = binding
    # Recipient acceptance is established separately by the caller. One local
    # stdin identity must never stand in for both independent recipients.
    save_receipt(
        target.with_suffix(target.suffix + ".json"),
        {"binding": binding, "recipients": sorted(set(recipients)), "result": result},
    )
    return result


def transfer(remote, command, target, recipient, identity, *, binding=None):
    original = target
    recipients = recipient if isinstance(recipient, list) else [recipient]
    if binding is not None:
        recovered = recover_transfer(target, recipients, identity, binding)
        if recovered is not None:
            return recovered
    partial = target.with_suffix(target.suffix + ".partial")
    if (
        target.exists()
        or partial.exists()
        or target.with_suffix(target.suffix + ".unverified").exists()
    ):
        raise ValueError("Existing archive requires review; refusing replacement")
    source = (
        remote.open_stream(command, privileged=True)
        if remote
        else subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    )
    encryption = None
    digest = hashlib.sha256()
    count = 0
    last_report = time.monotonic()
    try:
        source.stdin.close()
        with partial.open("xb") as output:
            encryption = subprocess.Popen(
                ["age", *[arg for value in recipients for arg in ["-r", value]]],
                stdin=subprocess.PIPE,
                stdout=output,
                stderr=subprocess.DEVNULL,
            )
            while chunk := source.stdout.read(4 * 1024 * 1024):
                digest.update(chunk)
                encryption.stdin.write(chunk)
                count += len(chunk)
                if time.monotonic() - last_report > 60:
                    print(
                        json.dumps(
                            {"component": target.name, "compressed_bytes": count}
                        ),
                        flush=True,
                    )
                    last_report = time.monotonic()
            encryption.stdin.close()
            source_code, encryption_code = source.wait(), encryption.wait()
            if source_code or encryption_code:
                raise ValueError(
                    f"Backup transfer failed (source={source_code}, "
                    f"encryption={encryption_code}); partial retained"
                )
            output.flush()
            os.fsync(output.fileno())
        if identity is not None:
            print(f"Authenticating complete archive {target.name}", flush=True)
            for key in identity if isinstance(identity, list) else [identity]:
                verify_archive(partial, key, digest.hexdigest())
        else:
            # No private identity is persisted on the unmigrated host. A separate
            # authenticated verification must publish this completed ciphertext.
            target = target.with_suffix(target.suffix + ".unverified")
        result = archive_result(target, digest.hexdigest(), count, identity is not None)
        if binding is not None:
            result["source_plan_sha256"] = binding
            # The durable completion record precedes publication, so a crash can
            # never leave a published archive without its independently
            # checkable digest.
            save_receipt(
                original.with_suffix(original.suffix + ".json"),
                {
                    "binding": binding,
                    "recipients": sorted(set(recipients)),
                    "result": result,
                },
            )
        # Publish without overwriting an existing backup.
        os.link(partial, target)
        partial.unlink()
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return result
    finally:
        source.stdout.close()
        for process in [source, encryption]:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()


def save_receipt(path, value):
    # Check both names before truncating or replacing anything on external media.
    read_receipt(path)
    temporary = path.with_suffix(".pending")
    with private_open(temporary, os.O_RDWR | os.O_CREAT) as stream:
        stream.seek(0)
        stream.truncate()
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    sync_directory(path.parent)


def local_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--destination-uuid", required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--custodian-recipient")
    parser.add_argument(
        "--recover-existing",
        action="store_true",
        help="With --verify, authenticate an orphan against a fresh "
        "current snapshot stream",
    )
    parser.add_argument(
        "--legacy-ssh-identity",
        action="store_true",
        help="Verify an existing SSH-encrypted archive only; never create a new one",
    )
    parser.add_argument("--verify", choices=list(snapshot_sources("gc-09")))
    args = parser.parse_args()
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if socket.gethostname() != "gc-09" or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]{5,60}", args.snapshot_id
    ):
        parser.error("Host-local backup is limited to the reviewed gc-09 snapshots")
    if (
        args.destination.resolve() != args.destination
        or not args.destination.is_mount()
    ):
        parser.error("Backup destination is not an exact existing mount")
    mounted = json.loads(
        subprocess.check_output(
            [
                "findmnt",
                "--json",
                "--mountpoint",
                str(args.destination),
                "--output",
                "UUID",
            ],
            text=True,
        )
    )["filesystems"][0]
    if mounted["uuid"] != args.destination_uuid:
        parser.error("Wrong backup filesystem identity")
    plan = json.loads(
        Path(
            f"/var/lib/luxnix-migration-snapshots/{args.snapshot_id}/plan.json"
        ).read_text()
    )
    if (
        not plan["complete"]
        or plan["host"] != "gc-09"
        or plan["identifier"] != args.snapshot_id
    ):
        parser.error("Snapshot plan incomplete or mismatched")
    if mounted["uuid"] in {fs["uuid"] for fs in plan["mounts"].values()}:
        parser.error("Backup must use a filesystem independent of all source snapshots")
    expected = set(snapshot_sources("gc-09"))
    if (
        len(plan["snapshots"]) != len(expected)
        or {i["name"] for i in plan["snapshots"]} != expected
    ):
        parser.error("Incomplete snapshot coverage")
    for item in plan["snapshots"]:
        validate_snapshot("gc-09", args.snapshot_id, item)
    root = args.destination / "luxnix-storage-migration" / f"gc-09-{args.snapshot_id}"
    if root.resolve() != root:
        parser.error("Symlink in backup destination")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    private_directory(root)
    lock = private_open(root / ".lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    receipt_path = root / "receipt.json"
    if (
        not re.fullmatch(r"age1[0-9a-z]{58}", args.recipient)
        or not args.custodian_recipient
        or not re.fullmatch(r"age1[0-9a-z]{58}", args.custodian_recipient)
        or args.recipient == args.custodian_recipient
    ):
        parser.error(
            "Specify distinct controller and independent custodian age recipients, "
            "including for verification"
        )
    receipt = bind_receipt(root, plan, [args.recipient, args.custodian_recipient])
    if args.verify:
        import sys

        target = root / f"{args.verify}.btrfs.gz.age"
        item = receipt["components"].get(args.verify)
        if item is None:
            item = recover_transfer(
                target, receipt["recipients"], None, receipt["source_plan_sha256"]
            )
            if item is None and not args.recover_existing:
                parser.error(
                    "No durable completed transfer record; use explicit "
                    "--recover-existing after review"
                )
        unverified = target.with_suffix(target.suffix + ".unverified")
        # Recovery identity exists only in an anonymous RAM descriptor, never in
        # an unencrypted host file, process argument, journal or Nix derivation.
        swaps = subprocess.check_output(
            ["swapon", "--show=NAME,TYPE", "--noheadings", "--raw"], text=True
        )
        for line in swaps.splitlines():
            fields = line.split()
            if (
                len(fields) != 2
                or fields[1] != "partition"
                or not re.fullmatch(r"/dev/zram[0-9]+", fields[0])
            ):
                parser.error("Recovery identity requires disabled disk swap")
            if (
                Path("/sys/block/" + Path(fields[0]).name + "/backing_dev")
                .read_text()
                .strip()
                != "none"
            ):
                parser.error("Recovery identity forbids zram writeback")
        fd = os.memfd_create("backup-recovery-identity", flags=0)
        try:
            key = sys.stdin.buffer.read(8193)
            if len(key) > 8192 or not (
                b"AGE-SECRET-KEY-1" in key
                or (
                    args.legacy_ssh_identity
                    and key.startswith(b"-----BEGIN OPENSSH PRIVATE KEY-----")
                )
            ):
                parser.error(
                    "Expected dedicated age recovery identity on stdin; existing SSH "
                    "archives require explicit legacy verification"
                )
            os.write(fd, key)
            del key
            os.lseek(fd, 0, os.SEEK_SET)
            if receipt.get("recipients"):
                identity_recipient = subprocess.check_output(
                    ["age-keygen", "-y", f"/proc/self/fd/{fd}"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    pass_fds=(fd,),
                ).strip()
                if identity_recipient not in receipt["recipients"]:
                    parser.error(
                        "Recovery identity is not one of the recorded "
                        "archive recipients"
                    )
                os.lseek(fd, 0, os.SEEK_SET)
            elif not args.legacy_ssh_identity:
                parser.error(
                    "Legacy archive verification requires the explicit legacy option"
                )
            if item is None:
                source = next(i for i in plan["snapshots"] if i["name"] == args.verify)
                prop = subprocess.check_output(
                    ["btrfs", "property", "get", "-ts", source["snapshot"], "ro"]
                )
                if prop.strip() != b"ro=true":
                    parser.error("Source snapshot is not read-only")
                pipeline = (
                    shlex.join(["btrfs", "send", source["snapshot"]]) + " | gzip -1"
                )
                # The anonymous descriptor must survive both authentication calls.
                item = recover_existing(
                    None,
                    ["bash", "-o", "pipefail", "-c", pipeline],
                    target,
                    receipt["recipients"],
                    [(Path(f"/proc/self/fd/{fd}"), fd)],
                    receipt["source_plan_sha256"],
                )
                receipt["components"][args.verify] = item
            verify_archive(
                target if target.exists() else unverified,
                Path(f"/proc/self/fd/{fd}"),
                item["sha256_compressed_stream"],
                pass_fds=(fd,),
            )
            verified = set(item.get("verified_recipients", []))
            if receipt.get("recipients"):
                verified.add(identity_recipient)
            authenticated = not receipt.get("recipients") or verified == set(
                receipt["recipients"]
            )
            if authenticated and not item["authenticated"]:
                if not target.exists():
                    os.link(unverified, target, follow_symlinks=False)
                    sync_directory(root)
                if unverified.exists():
                    if not os.path.samefile(unverified, target):
                        raise ValueError(
                            "Conflicting verification artifacts; "
                            "operator review required"
                        )
                    unverified.unlink()
                    sync_directory(root)
            receipt["components"][args.verify] = item
            item["authenticated"] = authenticated
            item["verified_recipients"] = sorted(verified)
            item["artifact"] = target.name if target.exists() else unverified.name
        finally:
            os.close(fd)
        receipt["complete"] = set(receipt["components"]) == expected and all(
            i["authenticated"] for i in receipt["components"].values()
        )
        save_receipt(receipt_path, receipt)
        print(
            "Archive recovery check: "
            + args.verify
            + (
                "; all recorded recipients verified"
                if item["authenticated"]
                else "; verify the other independent recipient before acceptance"
            ),
            flush=True,
        )
        return
    if args.recover_existing:
        parser.error(
            "--recover-existing requires --verify with an independent recovery identity"
        )
    if args.legacy_ssh_identity:
        parser.error("Legacy SSH identities may only verify existing archives")
    if receipt.get("recipients") != sorted([args.recipient, args.custodian_recipient]):
        parser.error(
            "Existing archive recipient selection differs; retain it "
            "and use a new backup identifier"
        )
    for item in plan["snapshots"]:
        name = item["name"]
        if name in receipt["components"]:
            continue
        prop = subprocess.check_output(
            ["btrfs", "property", "get", "-ts", item["snapshot"], "ro"]
        )
        if prop.strip() != b"ro=true":
            parser.error("Source snapshot is not read-only")
        pipeline = shlex.join(["btrfs", "send", item["snapshot"]]) + " | gzip -1"
        print("Encrypting host-local snapshot " + name, flush=True)
        receipt["components"][name] = transfer(
            None,
            ["bash", "-o", "pipefail", "-c", pipeline],
            root / f"{name}.btrfs.gz.age",
            [args.recipient, args.custodian_recipient],
            None,
            binding=receipt["source_plan_sha256"],
        )
        save_receipt(receipt_path, receipt)
    print(
        "Ciphertext creation complete; authenticate each component before restore",
        flush=True,
    )


if __name__ == "__main__":
    local_main()
