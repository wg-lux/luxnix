"""Encrypted, non-overwriting credential archives with host and path drift checks.

No password rotation, deletion, formatting, installation or automatic acceptance.
Plaintext exists only in memory; protected swap and disabled core dumps are required.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import resource
import stat
import subprocess
import tarfile
from typing import Literal

from pydantic import BaseModel, ConfigDict

from lx_administration.secret_storage import _require_protected_swap, filesystem_devices
from lx_administration.storage import boot_migration as migration
from lx_administration.storage import recovery_custody as custody
from lx_administration.storage import secret_preflight as preflight
from lx_administration.utils.file_operations import atomic_create_file
from lx_administration.yaml import load_unique_yaml_file

POLICY = Path(__file__).with_name("credential-backup-policy.yml")
STALE = (
    "Backup no longer verifies this host's current credentials or paths. "
    "Keep the old archive for recovery. Review/revert the change, or update the "
    "recovery test and create a NEW backup; do not edit its manifest or reuse "
    "old approval."
)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileRecord(Record):
    path: str
    sha256: str
    mode: int
    uid: int
    gid: int


class Manifest(Record):
    schema_version: Literal[1] = 1
    plan_id: str
    source: dict[str, str]
    generation: str
    contract: dict
    roots: dict[str, dict | None]
    destination: dict
    recipient: str
    policy_sha256: str
    files: list[FileRecord]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_plan(state: Path) -> dict:
    # sudo may read the invoking operator's immutable plan, but never rewrite it.
    path = state / "plan.json"
    owners = {0, int(os.environ.get("SUDO_UID", os.getuid()))}
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("Plan path must be absolute and without symlinks")
    for parent in path.parents:
        if parent.stat().st_mode & 0o022:
            raise ValueError("Plan parent is writable by another user")
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid not in owners
        or info.st_mode & 0o077
    ):
        raise ValueError(
            "Plan must be a private file owned by root or the invoking user"
        )
    plan = json.loads(path.read_bytes())
    migration.exact_keys(
        plan, {"schema_version", "spec", "source", "config", "plan_id"}, "Plan"
    )
    if plan["schema_version"] != 1 or plan["plan_id"] != migration.digest(
        {k: v for k, v in plan.items() if k != "plan_id"}
    ):
        raise ValueError("Invalid plan binding")
    migration.validate_spec(plan["spec"])
    verify_source(plan)
    preflight.require_target_host(plan)
    return plan


def verify_source(plan: dict) -> None:
    # The operator explicitly runs this reviewed checkout via sudo. Trust only
    # this exact repository for Git's ownership check; never change Git config.
    checkout = Path(plan["spec"]["checkout"])
    if (
        not checkout.is_absolute()
        or checkout.resolve() != checkout
        or Path("/tmp") in checkout.parents
        or checkout == Path("/tmp")
    ):
        raise ValueError("Use the reviewed durable checkout, not a temporary source")
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if migration.run(*git, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError(
            "Reviewed checkout is dirty; preserve it and review before backup"
        )
    source = {
        "revision": migration.run(*git, "rev-parse", "HEAD"),
        "lock_sha256": migration.file_digest(checkout / "flake.lock"),
    }
    if source != plan["source"]:
        raise ValueError(STALE)


def extra_contract(plan: dict) -> dict:
    """Read paths only; the password values never enter Nix evaluation."""
    expression = """let f = builtins.getFlake CHECKOUT;
      c = f.nixosConfigurations.HOST.config; v = c.luxnix.vault;
      a = c.user.admin.name;
    in {
      account_sources = c.luxnix.storage.operatorUnlocked.migration.accountHashes;
      accounts = { ${a} = c.users.users.${a}.hashedPasswordFile; }
        // (if c.user.client.enable then {
          ${c.user.client.name} =
            c.users.users.${c.user.client.name}.hashedPasswordFile;
        } else { });
      ssh_keys = map (k: k.path) c.services.openssh.hostKeys;
      admin_home = c.users.users.${a}.home;
      vault_paths = [ v.dir v.adminPasswordFile v.adminPasswordHashedFile v.key v.psk ];
      secret_root = c.luxnix.generic-settings.secretDir;
    }""".replace(
        "CHECKOUT", json.dumps("git+file://" + plan["spec"]["checkout"])
    ).replace("HOST", plan["spec"]["host"])
    return json.loads(
        migration.run(
            "nix",
            "eval",
            "--no-update-lock-file",
            "--impure",
            "--json",
            "--expr",
            expression,
            timeout=600,
        )
    )


def verify_accounts(extra: dict) -> None:
    from lx_administration.storage.operator_migration import validate_account_hash

    for name, path in extra["accounts"].items():
        if not path:
            raise ValueError(f"Account {name} lacks a recoverable declared hash")
        saved = validate_account_hash(Path(path).read_bytes()).strip()
        live = migration.run("getent", "-s", "files", "shadow", name).split(":")
        if len(live) < 2 or not hmac.compare_digest(saved, live[1].encode()):
            raise ValueError(
                f"Account {name} differs from its boot hash; "
                "reconcile explicitly before backup"
            )


def filesystem(path: Path, seen: tuple[str, ...] = ()) -> dict:
    if str(path) in seen or len(seen) >= 8:
        raise ValueError("Cyclic or excessive loop-backed storage topology")
    fs = json.loads(
        migration.run(
            "findmnt",
            "--json",
            "--target",
            str(path),
            "--output",
            "SOURCE,FSTYPE,UUID,FSROOT",
        )
    )["filesystems"]
    if len(fs) != 1 or not fs[0].get("uuid"):
        raise ValueError(f"No unambiguous persistent filesystem identity for {path}")
    disks = []
    loops = {}
    for device in filesystem_devices(fs[0]):
        rows = json.loads(
            migration.run(
                "lsblk",
                "--json",
                "--bytes",
                "--paths",
                "--inverse",
                "--output",
                "NAME,TYPE,SERIAL,SIZE",
                device,
            )
        )["blockdevices"]
        for row in migration.walk(rows):
            if row.get("children"):
                continue
            if row["type"] == "loop":
                loop = json.loads(
                    migration.run(
                        "losetup",
                        "--list",
                        "--json",
                        "--output",
                        "NAME,BACK-FILE",
                        row["name"],
                    )
                )["loopdevices"]
                if len(loop) != 1 or loop[0]["name"] != row["name"]:
                    raise ValueError("Ambiguous legacy container backing file")
                backing = Path(loop[0]["back-file"])
                identity = filesystem(backing, (*seen, str(path)))
                loops[str(backing)] = identity
                disks.extend(identity["disks"])
            elif row["type"] == "disk" and row.get("serial"):
                disks.append({"serial": row["serial"], "size": int(row["size"])})
            else:
                raise ValueError("Storage does not resolve to stable physical disks")
    if not disks:
        raise ValueError("No physical backing disks found")
    # Linux device names and mount locations may change; physical identities must not.
    return {
        "uuid": fs[0]["uuid"],
        "fstype": fs[0]["fstype"],
        "fsroot": fs[0]["fsroot"],
        "containers": loops,
        "disks": sorted(disks, key=lambda d: d["serial"]),
    }


def selected_roots(
    plan: dict, extra: dict, policy: dict
) -> tuple[set[Path], set[Path]]:
    contract = plan["config"].get("secret_contract")
    if contract is None:
        raise ValueError("Plan lacks the evaluated secret contract; review a new plan")
    if contract["vault_server"] or contract["openbao"]:
        raise ValueError(
            "Secrets-server data/unseal recovery requires the Vault server workflow"
        )
    required = {Path(i["path"]) for i in contract["items"]}
    required.update(Path(i["path"]) for i in preflight.retained_volume_keys(plan))
    required.update(Path(p) for p in extra["ssh_keys"])
    if any(not p for p in extra["accounts"].values()):
        raise ValueError("Every enabled account needs a declared recovery hash")
    required.update(Path(p) for p in extra["accounts"].values())
    # Preserve both the authoritative boot copies and their initialization sources.
    required.update(Path(p) for p in extra["account_sources"])
    required.update(Path(p) for p in extra["account_sources"].values())
    optional = {Path(p) for p in policy["optional_paths"] + extra["vault_paths"]}
    optional.add(Path(extra["secret_root"]))
    home = Path(extra["admin_home"])
    if (home / ".lxv").exists() != (home / ".lxv.key").exists():
        raise ValueError("Controller Vault and unlocking key must both be available")
    optional.update((home / ".lxv", home / ".lxv.key"))
    return required, optional - required


def collect(
    roots: set[Path], required: set[Path], policy: dict
) -> tuple[dict, dict, list[FileRecord]]:
    identities, contents = {}, {}
    records = []
    total = 0
    for root in sorted(roots):
        if not root.is_absolute() or root.resolve() != root:
            raise ValueError(f"Credential path is relative or symlinked: {root}")
        if not root.exists():
            if root in required:
                raise ValueError(f"Required credential is missing or locked: {root}")
            identities[str(root)] = None
            continue
        identities[str(root)] = filesystem(root)
        paths = [root] if not root.is_dir() else sorted(root.rglob("*"))
        for path in paths:
            if path.is_symlink():
                raise ValueError(f"Review symlinked credential explicitly: {path}")
            if path.is_dir():
                continue
            name = str(path)
            if name in contents:
                continue
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError(f"Credential is not a regular file: {path}")
                if (
                    total + before.st_size > policy["max_bytes"]
                    or len(contents) >= policy["max_files"]
                ):
                    raise ValueError(
                        "Credential scope exceeds policy limit; "
                        "review instead of skipping files"
                    )
                data = stream.read(policy["max_bytes"] - total + 1)
                after = os.fstat(stream.fileno())
                attributes = (
                    "st_dev",
                    "st_ino",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                    "st_mode",
                    "st_uid",
                    "st_gid",
                )
                if (
                    any(getattr(before, k) != getattr(after, k) for k in attributes)
                    or len(data) != before.st_size
                ):
                    raise ValueError(
                        "Credential changed during read; retry after writers stop"
                    )
            total += len(data)
            contents[name] = data
            records.append(
                FileRecord(
                    path=name,
                    sha256=digest(data),
                    mode=stat.S_IMODE(before.st_mode),
                    uid=before.st_uid,
                    gid=before.st_gid,
                )
            )
    return identities, contents, sorted(records, key=lambda f: f.path)


def pack(manifest: Manifest, contents: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        data = manifest.model_dump_json().encode()
        member = tarfile.TarInfo("manifest.json")
        member.size, member.mode = len(data), 0o600
        archive.addfile(member, io.BytesIO(data))
        for record in manifest.files:
            member = tarfile.TarInfo("files/" + record.path.lstrip("/"))
            member.size, member.mode = len(contents[record.path]), record.mode
            member.uid, member.gid = record.uid, record.gid
            archive.addfile(member, io.BytesIO(contents[record.path]))
    return output.getvalue()


def unpack(data: bytes) -> Manifest:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        members = archive.getmembers()
        if any(not m.isfile() for m in members):
            raise ValueError("Unexpected archive member type")
        manifest = Manifest.model_validate_json(
            archive.extractfile("manifest.json").read()
        )
        names = ["manifest.json"] + [
            "files/" + f.path.lstrip("/") for f in manifest.files
        ]
        if sorted(names) != sorted(m.name for m in members) or len(set(names)) != len(
            names
        ):
            raise ValueError("Archive member set differs from manifest")
        for record in manifest.files:
            if not Path(record.path).is_absolute() or ".." in Path(record.path).parts:
                raise ValueError("Unsafe archive path")
            member = archive.getmember("files/" + record.path.lstrip("/"))
            if digest(archive.extractfile(member).read()) != record.sha256 or (
                member.mode,
                member.uid,
                member.gid,
            ) != (record.mode, record.uid, record.gid):
                raise ValueError("Archive content or ownership verification failed")
        return manifest


def crypt(arguments: list[str], data: bytes) -> bytes:
    result = subprocess.run(
        ["age", *arguments], input=data, capture_output=True, timeout=600
    )
    if result.returncode:
        raise ValueError(
            "Archive encryption/authentication failed; no credential values were logged"
        )
    return result.stdout


def execute(state: Path, archive: Path, identity: Path | None, *, action: str) -> None:
    if os.geteuid() != 0:
        raise ValueError(
            "Run this local backup command through sudo; never run sudo devenv"
        )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    _require_protected_swap()
    plan = read_plan(state)
    policy = load_unique_yaml_file(POLICY)
    extra = extra_contract(plan)
    required, optional = selected_roots(plan, extra, policy)
    print(
        f"Host: {plan['spec']['host']}; credentials only, "
        "no password changes or deletion."
    )
    for path in sorted(required | optional):
        print(f"{'required' if path in required else 'optional'}: {path}")
    print(
        "Retirement candidates require consumer review; "
        "none are automatically excluded."
    )
    if not archive.is_absolute() or archive.resolve() != archive:
        raise ValueError("Archive needs an absolute path without symlinks")
    migration.private_path(archive.parent, directory=True)
    destination = filesystem(archive.parent)
    selected = {d["serial"] for d in plan["spec"]["disks"]}
    if selected & {d["serial"] for d in destination["disks"]}:
        raise ValueError("Backup destination is on a disk selected for erasure")
    if action == "preview":
        print(
            "Preview only. No credentials copied. "
            "Identity and live files are checked on backup/verify."
        )
        return
    if identity is None:
        raise ValueError(
            "Select an existing independent native age identity with --identity"
        )
    recipient = custody.recipient(identity)
    custody.independent(identity, archive.parent)
    if selected & {d["serial"] for d in filesystem(identity)["disks"]}:
        raise ValueError("Archive unlocking identity is on a disk selected for erasure")
    if action == "backup" and archive.exists():
        raise ValueError(
            "Archive already exists; use a new name, never overwrite recovery"
        )
    verify_accounts(extra)
    roots, contents, records = collect(required | optional, required, policy)
    source_disks = {d["serial"] for fs in roots.values() if fs for d in fs["disks"]}
    if source_disks & {d["serial"] for d in destination["disks"]}:
        raise ValueError(
            "Recovery drive shares a physical disk with a credential source"
        )
    manifest = Manifest(
        plan_id=plan["plan_id"],
        source=plan["source"],
        generation=str(Path("/run/current-system").resolve(strict=True)),
        contract={"secrets": plan["config"]["secret_contract"], "extra": extra},
        roots=roots,
        destination=destination,
        recipient=recipient,
        policy_sha256=digest(POLICY.read_bytes()),
        files=records,
    )
    if action == "verify":
        migration.private_path(archive)
        if archive.stat().st_size > policy["max_bytes"] * 3:
            raise ValueError("Archive exceeds credential policy size limit")
        actual = unpack(crypt(["-d", "-i", str(identity)], archive.read_bytes()))
        if actual != manifest:
            raise ValueError(STALE)
    else:
        encrypted = crypt(["-r", recipient], pack(manifest, contents))
        if unpack(crypt(["-d", "-i", str(identity)], encrypted)) != manifest:
            raise ValueError("Archive round-trip verification failed")
    # Detect concurrent writes, generation or mount changes in both operations.
    if collect(required | optional, required, policy) != (roots, contents, records):
        raise ValueError(STALE)
    verify_source(plan)
    if (
        filesystem(archive.parent) != destination
        or str(Path("/run/current-system").resolve(strict=True)) != manifest.generation
    ):
        raise ValueError(STALE)
    if action == "backup":
        atomic_create_file(destination=archive, content=[encrypted], file_mode=0o600)
    print(
        json.dumps(
            {
                "event": "credential_backup_" + action,
                "archive": str(archive),
                "plan_id": plan["plan_id"],
                "files": len(records),
            }
        )
    )
    print(
        "Archive verified. This does not approve disk erasure "
        "or replace secret preflight/restore tests."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preview", "backup", "verify"])
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--identity", type=Path)
    args = parser.parse_args()
    try:
        execute(args.state, args.archive, args.identity, action=args.action)
    except (
        ValueError,
        OSError,
        tarfile.TarError,
        KeyError,
        subprocess.SubprocessError,
    ) as error:
        parser.exit(
            1,
            f"Credential backup stopped: {error}\n"
            "No approval to erase. Keep existing archives.\n",
        )


if __name__ == "__main__":
    main()
