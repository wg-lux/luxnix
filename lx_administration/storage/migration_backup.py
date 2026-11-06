"""Stream existing read-only Btrfs snapshots to authenticated encrypted backups.

No restore, reboot, activation, formatting, snapshot deletion or key generation.
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
import shlex
import subprocess

from lx_administration.autoconf import AutoconfConfig, DEFAULT_CONFIG_PATH
from lx_administration.models.ansible.inventory import AnsibleInventory
from lx_administration.secret_storage import encrypted_storage
from lx_administration.storage.provision import Remote
from lx_administration.storage.recovery_custody import verify_pair


from lx_administration.storage.migration_archive import (
    validate_snapshot,
    verify_archive,
    transfer,
    private_open,
    private_directory,
    bind_receipt,
    save_receipt,
    recover_existing,
)
from lx_administration.storage.migration_policy import snapshot_sources, supported_hosts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recover-existing",
        action="store_true",
        help="Authenticate orphan archives against fresh current snapshot "
        "streams before adoption",
    )
    parser.add_argument("--host", required=True, choices=supported_hosts())
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--custodian-identity", required=True, type=Path)
    parser.add_argument("--sudo-password-file", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{5,60}", args.snapshot_id):
        parser.error("Invalid snapshot identifier")
    for path in [args.identity, args.sudo_password_file]:
        encrypted_storage(path)
        if not path.is_file() or path.stat().st_mode & 0o077:
            parser.error(
                "Recovery identity and sudo file must be existing private files "
                "on encrypted storage"
            )
    if (
        args.destination.resolve() != args.destination
        or not args.destination.is_mount()
    ):
        parser.error(
            "Destination must be an existing exact mounted filesystem without symlinks"
        )
    custody = verify_pair(args.identity, args.custodian_identity)
    recipients = custody["recipients"]
    config = AutoconfConfig.load(DEFAULT_CONFIG_PATH)
    inventory = AnsibleInventory.load_from_hosts_ini(
        config.ansible_root / "inventory/hosts.ini", config.inventory_subnet
    )
    host = inventory.get_host_by_name(args.host)
    if host is None:
        parser.error("Unknown inventory target")
    remote = Remote(str(host.ansible_host), args.sudo_password_file)
    if remote.call(["hostname"]).decode().strip() != args.host:
        parser.error("Remote host identity mismatch")
    plan_path = f"/var/lib/luxnix-migration-snapshots/{args.snapshot_id}/plan.json"
    plan = json.loads(remote.call(["cat", plan_path], privileged=True))
    if (
        not plan["complete"]
        or plan["host"] != args.host
        or plan["identifier"] != args.snapshot_id
    ):
        parser.error("Snapshot plan incomplete or mismatched; inspect recovery errors")
    expected = set(snapshot_sources(args.host))
    if (
        len(plan["snapshots"]) != len(expected)
        or {i["name"] for i in plan["snapshots"]} != expected
    ):
        parser.error("Snapshot coverage incomplete")
    for item in plan["snapshots"]:
        validate_snapshot(args.host, args.snapshot_id, item)
    root = (
        args.destination
        / "luxnix-storage-migration"
        / f"{args.host}-{args.snapshot_id}"
    )
    if root.resolve() != root:
        parser.error("Backup directory may not contain symlinks")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_directory(root)
    with private_open(root / ".lock", os.O_RDWR | os.O_CREAT) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt_path = root / "receipt.json"
        receipt = bind_receipt(
            root,
            plan,
            recipients,
            {
                "recovery_identity": str(args.identity),
                "custodian_identity": str(args.custodian_identity),
                "custody": custody,
                "tool_sha256": hashlib.sha256(
                    b"".join(
                        Path(__file__).with_name(name).read_bytes()
                        for name in (
                            "migration_backup.py",
                            "migration_archive.py",
                            "migration_policy.py",
                            "migration-policy.yml",
                        )
                    )
                ).hexdigest(),
                "source_revision": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], text=True
                ).strip(),
            },
        )
        # Every declared component is independently authenticated.
        for item in plan["snapshots"]:
            name = item["name"]
            target = root / f"{name}.btrfs.gz.age"
            if name in receipt["components"]:
                verify_archive(
                    target,
                    args.identity,
                    receipt["components"][name]["sha256_compressed_stream"],
                )
                verify_archive(
                    target,
                    args.custodian_identity,
                    receipt["components"][name]["sha256_compressed_stream"],
                )
                continue
            prop = remote.call(
                ["btrfs", "property", "get", "-ts", item["snapshot"], "ro"],
                privileged=True,
            )
            if prop.strip() != b"ro=true":
                raise ValueError("Snapshot is not read-only")
            pipeline = shlex.join(["btrfs", "send", item["snapshot"]]) + " | gzip -1"
            print(f"Backing up {args.host} {name}", flush=True)
            command = ["bash", "-o", "pipefail", "-c", pipeline]
            if (
                args.recover_existing
                and target.exists()
                and not target.with_suffix(target.suffix + ".json").exists()
            ):
                component = recover_existing(
                    remote,
                    command,
                    target,
                    recipients,
                    [args.identity, args.custodian_identity],
                    receipt["source_plan_sha256"],
                )
                component["authenticated"] = True
            else:
                component = transfer(
                    remote,
                    command,
                    target,
                    recipients,
                    [args.identity, args.custodian_identity],
                    binding=receipt["source_plan_sha256"],
                )
            receipt["components"][name] = component
            save_receipt(receipt_path, receipt)
        receipt["complete"] = True
        receipt["latest_custody_verification"] = verify_pair(
            args.identity, args.custodian_identity
        )
        save_receipt(receipt_path, receipt)
        print(
            "Snapshot archives authenticated; application restore and independent "
            "recovery custody remain required",
            flush=True,
        )


if __name__ == "__main__":
    main()
