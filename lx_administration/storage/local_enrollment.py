"""Cataloged, inventory-scoped local OpenBao enrollment with escrow before use.

Controller side of luxnix-openbao-local (openbao_enroll.py). Every secret that
can open a store or a volume is authenticated in the admin vault and on an
independent recovery host before the host may depend on it: the seal key before
it is TPM-sealed, the recovery key and provisioner credential before the root
token is revoked. Without --apply only read-only status and plans are shown.
Records are keyed by inventory host; machine-id is an attribute only.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

from lx_administration.autoconf import AutoconfConfig, DEFAULT_CONFIG_PATH
from lx_administration.models.ansible.inventory import AnsibleInventory
from lx_administration.models.vault import Vault
from lx_administration.models.vault.secret import (
    MASTER_VAULT_ID, _encrypt_bytes, _publish_ciphertext, decrypt_secret,
)
from lx_administration.permissions import ensure_private_directory
from lx_administration.secret_storage import encrypted_storage
from lx_administration.storage.provision import ProvisionError, Remote, escrow_record, EXPORT

FLEET_GROUP = "operator_unlocked_secrets"
ESCROW_ROOT = "openbao-local"
NAME = re.compile(r"[a-z0-9][a-z0-9-]*")

# Publishes ciphertext under ~/.luxnix-recovery/openbao-local/<host>/<item>.vault.
# No secret values are interpolated into this code or its arguments.
LOCAL_EXPORT = r'''
import fcntl, os, re, sys, tempfile
from pathlib import Path
host, item = sys.argv[1:]
assert re.fullmatch(r'[a-z0-9][a-z0-9-]*', host) and item in ('seal-key', 'enrollment')
data = sys.stdin.buffer.read()
assert data.startswith(b'$ANSIBLE_VAULT;1.2;AES256;luxnix-master\n')
root = Path.home() / '.luxnix-recovery'
for directory in [root, root / 'openbao-local', root / 'openbao-local' / host]:
    directory.mkdir(mode=0o700, exist_ok=True)
    assert not directory.is_symlink()
    info = directory.stat()
    assert info.st_uid == os.geteuid() and info.st_mode & 0o777 == 0o700
with (root / '.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    target = root / 'openbao-local' / host / (item + '.vault')
    assert not target.is_symlink()
    if target.exists():
        assert target.stat().st_mode & 0o777 == 0o600
        assert target.read_bytes() == data, 'Conflicting recovery export'
    else:
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.recovery-')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, target)
        finally: os.unlink(temporary)
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
    sys.stdout.buffer.write(target.read_bytes())
'''


class EnrollmentError(RuntimeError):
    """An operator-safe diagnostic without credential values."""


def escrow_path(vault: Path, host: str, item: str) -> Path:
    return vault / ESCROW_ROOT / host / (item + ".vault")


def load_escrow(vault: Path, vault_key: Path, host: str, item: str) -> dict | None:
    target = escrow_path(vault, host, item)
    if not target.exists():
        return None
    record = json.loads(decrypt_secret(target, vault_key))
    if record.get("host") != host or record.get("item") != item:
        raise EnrollmentError("Escrow record identity does not match its location")
    return record


def escrow(vault: Path, vault_key: Path, record: dict, export) -> Path:
    """Publish once, authenticate both copies, never replace existing material."""
    target = escrow_path(vault, record["host"], record["item"])
    ensure_private_directory(target.parent)
    expected = json.dumps(record, sort_keys=True).encode()
    if target.exists():
        if decrypt_secret(target, vault_key) != expected:
            raise EnrollmentError(f"{record['item']} escrow conflicts with the existing vault record")
    else:
        _publish_ciphertext(_encrypt_bytes(expected, vault_key, MASTER_VAULT_ID), target, replace=False)
    if decrypt_secret(target, vault_key) != expected:
        raise EnrollmentError("Primary escrow record failed authentication")
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    ciphertext = target.read_bytes()
    if export(ciphertext) != ciphertext:
        raise EnrollmentError("Independent recovery export did not return the stored ciphertext")
    return target


def digest(escrow_material: dict) -> str:
    # Same canonical form as openbao_enroll.escrow_digest on the host.
    return hashlib.sha256(json.dumps(escrow_material, sort_keys=True).encode()).hexdigest()


class Controller:
    """One host at a time; every phase is safe to repeat after an interruption."""

    def __init__(self, host, target, recovery, vault, vault_key, machine_id, local):
        self.host = host
        self.target = target
        self.recovery = recovery
        self.vault = vault
        self.vault_key = vault_key
        self.machine_id = machine_id
        self.local = local

    def tool(self, *args, request: dict | None = None) -> dict:
        data = b"" if request is None else json.dumps(request).encode()
        result = json.loads(self.target.call(["luxnix-openbao-local", *args], data, privileged=True,
                                             relay_error=True))
        if args[0] in {"status", "preflight"} and result.get("host") != self.host:
            raise EnrollmentError("Remote host name does not match the inventory host")
        return result

    def export(self, item):
        return lambda ciphertext: self.recovery.call(["python3", "-c", LOCAL_EXPORT, self.host, item],
                                                     ciphertext)

    def record(self, item: str, **values) -> dict:
        return {"schema_version": 1, "host": self.host, "item": item, "machine_id": self.machine_id,
                "seal_key_id": self.local["sealKeyId"], **values}

    def enroll(self) -> dict:
        status = self.tool("preflight")
        if status["enrolled"]:
            existing = load_escrow(self.vault, self.vault_key, self.host, "enrollment")
            if existing is None:
                raise EnrollmentError("Host is enrolled but no enrollment escrow exists; use recovery")
            escrow(self.vault, self.vault_key, existing, self.export("enrollment"))
            return {"host": self.host, "enrolled": True, "escrow_verified": True}
        # 1. Seal key: escrowed before the host ever depends on it.
        seal = load_escrow(self.vault, self.vault_key, self.host, "seal-key")
        if seal is None:
            if status["initialized"]:
                raise EnrollmentError("Host has a local store but no escrowed seal key; use recovery")
            seal = self.record("seal-key", seal_key=base64.b64encode(secrets.token_bytes(32)).decode())
        if seal["seal_key_id"] != self.local["sealKeyId"]:
            raise EnrollmentError("Escrowed seal key id differs from the declared sealKeyId")
        escrow(self.vault, self.vault_key, seal, self.export("seal-key"))
        self.tool("seal", request={"seal_key": seal["seal_key"]})
        # 2. Initialize (or resume), then escrow recovery key and provisioner.
        material = self.tool("initialize")["escrow"]
        record = self.record("enrollment", **material)
        escrow(self.vault, self.vault_key, record, self.export("enrollment"))
        # 3. Only now may the host revoke the root token.
        self.tool("confirm", request={"escrow_sha256": digest(material)})
        return {"host": self.host, "enrolled": True, "escrow_verified": True}

    def provisioner(self) -> dict:
        record = load_escrow(self.vault, self.vault_key, self.host, "enrollment")
        if record is None:
            raise EnrollmentError("No enrollment escrow for this host; enroll first")
        return record["provisioner"]

    def adopt(self, name: str, volume: dict, apply: bool, *, open_mapping=False) -> dict:
        identity = ["--volume", name, "--container", volume["container"], "--luks-uuid", volume["luksUUID"]]
        plan = self.tool("plan-volume", *identity)
        if not apply:
            return plan
        source = self.vault / "storage-recovery" / self.machine_id / (name + ".vault")
        if not source.exists():
            raise EnrollmentError("No escrowed recovery passphrase for this volume; run storage-provision escrow")
        recovery = json.loads(decrypt_secret(source, self.vault_key))
        if (recovery["host"] != self.host or recovery["volume"] != name
                or recovery["luks_uuid"] != volume["luksUUID"] or recovery["container"] != volume["container"]):
            raise EnrollmentError("Recovery escrow does not match the declared volume")
        # Re-authenticates the primary copy and the independent export before any keyslot change.
        escrow_record(self.vault, self.vault_key, recovery, lambda ciphertext: self.recovery.call(
            ["python3", "-c", EXPORT, self.machine_id, recovery["luks_uuid"]], ciphertext))
        request = {"recovery_passphrase": recovery["recovery_passphrase"], "provisioner": self.provisioner()}
        if open_mapping:
            request["open_mapping"] = volume["device"].removeprefix("/dev/mapper/")
        result = self.tool("convert-volume", *identity, request=request)
        return dict(result, planned=plan["changes"])

    def rotate_unlock(self) -> dict:
        self.tool("preflight")
        return dict(self.tool("rotate-unlock", request={"provisioner": self.provisioner()}), host=self.host)

    def rollout(self, volumes, provision_missing, *, migration_enabled, apply=False, cutover=False) -> dict:
        """One ordered wave: enroll, provision/adopt, pre-copy, optional final cutover."""
        if not migration_enabled:
            raise EnrollmentError("Rollout requires operator storage migration enabled in the selected configuration")
        for unit in ("luxnix-storage-precopy.service", "luxnix-storage-cutover.service"):
            state = self.target.call(["systemctl", "show", "--property=LoadState", "--value", unit])
            if state.strip() != b"loaded":
                raise EnrollmentError(f"Rollout requires deployed unit {unit} (load state: {state.decode(errors='replace').strip()})")
        status = self.tool("preflight")
        plans = []
        for name, volume in volumes.items():
            if not volume.get("container") or not volume.get("luksUUID"):
                raise EnrollmentError("Rollout requires declared container paths and native LUKS UUIDs")
            present = self.target.call(['sh', '-c', 'test ! -e "$1" || printf present',
                                        'probe', volume['container']]).strip() == b'present'
            plans.append((name, volume, present))
        if not apply:
            return {"host": self.host, "enrolled": status["enrolled"], "apply": False,
                    "volumes": [{"volume": name, "action": "adopt" if present else "provision"}
                                for name, _, present in plans], "cutover": cutover}
        self.enroll()
        for name, volume, present in plans:
            recovery_path = self.vault / "storage-recovery" / self.machine_id / (name + ".vault")
            recovery = json.loads(decrypt_secret(recovery_path, self.vault_key)) if recovery_path.exists() else {}
            if present and recovery.get("origin") != "new":
                self.adopt(name, volume, apply=True, open_mapping=True)
            else:
                provision_missing(name)
        self.target.call(["systemctl", "start", "luxnix-storage-precopy.service"], privileged=True)
        if cutover:
            self.target.call(["systemctl", "start", "luxnix-storage-cutover.service"], privileged=True)
        return {"host": self.host, "precopy": True, "cutover": cutover}


def nix_eval(host: str, attribute: str):
    expression = f".#nixosConfigurations.{host}.config.{attribute}"
    result = subprocess.run(["nix", "eval", "--json", expression], capture_output=True, check=False)
    if result.returncode:
        raise EnrollmentError(f"Cannot evaluate {attribute} for {host}")
    return json.loads(result.stdout)


def select_hosts(inventory, limit: str) -> list[str]:
    """A host or group name; every selected host must belong to the fleet group."""
    names = inventory.get_hostnames()
    if limit in names:
        selected = [limit]
    elif inventory.group_name_exists(limit):
        selected = [h.hostname for h in inventory.all if limit in h.ansible_group_names]
    else:
        raise EnrollmentError("--limit is neither an inventory host nor a group")
    outside = [h.hostname for h in inventory.all
               if h.hostname in selected and FLEET_GROUP not in h.ansible_group_names]
    if not selected or outside:
        raise EnrollmentError(f"Selection must be non-empty and inside {FLEET_GROUP}")
    return sorted(selected)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["status", "enroll", "adopt", "rotate-unlock", "rollout"])
    parser.add_argument("--limit", required=True, help="Inventory host or group")
    parser.add_argument("--volume", action="append", default=[], help="adopt only; default all declared")
    parser.add_argument("--recovery-host", help="Independent emergency export host")
    parser.add_argument("--vault-dir", type=Path, default=Path.home() / ".lxv")
    parser.add_argument("--vault-key", type=Path, default=Path.home() / ".lxv.key")
    parser.add_argument("--sudo-password-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cutover", action="store_true", help="rollout only: stop writers for the final verified copy")
    args = parser.parse_args(argv)
    if args.cutover and args.action != "rollout":
        parser.error("--cutover requires rollout")
    if args.action == "rollout" and args.volume:
        parser.error("rollout covers all declared volumes; --volume is for adoption")
    for value in [args.recovery_host or "x", *args.volume]:
        if not NAME.fullmatch(value):
            parser.error("Host and volume names must be canonical inventory identifiers")
    config = AutoconfConfig.load(DEFAULT_CONFIG_PATH)
    inventory = AnsibleInventory.load_from_hosts_ini(
        config.ansible_root / "inventory/hosts.ini", config.inventory_subnet)

    def remote(host, password=None):
        entry = inventory.get_host_by_name(host)
        if entry is None:
            raise EnrollmentError("Host is not in the inventory")
        return Remote(str(entry.ansible_host), password)

    hosts = select_hosts(inventory, args.limit)
    mutating = args.apply and args.action != "status"
    if mutating:
        if not args.recovery_host or args.recovery_host in hosts:
            raise EnrollmentError("--recovery-host must name a separate inventory host")
        if not args.vault_dir.is_dir():
            raise EnrollmentError("Existing admin vault directory is required")
        encrypted_storage(args.vault_key, allow_runtime=True)
        Vault.load_dir(str(args.vault_dir), str(args.vault_key)).validate_local_key()
        recovery = remote(args.recovery_host)
        controller_id = Path("/etc/machine-id").read_text().strip()
        lock_dir = ensure_private_directory(args.vault_dir / ESCROW_ROOT)
        lock = (lock_dir / ".lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_EX)
    failures = 0
    for host in hosts:
        try:
            local = nix_eval(host, "luxnix.openbao.local")
            if not local["enable"]:
                raise EnrollmentError("luxnix.openbao.local.enable is not deployed for this host")
            target = remote(host, args.sudo_password_file)
            machine_id = target.machine_id()
            if mutating and recovery.machine_id() in {machine_id, controller_id}:
                raise EnrollmentError("Emergency export must be separate from target and admin vault")
            controller = Controller(host, target, recovery if mutating else None,
                                    args.vault_dir, args.vault_key, machine_id, local)
            if args.action in {"adopt", "rollout"}:
                volumes = nix_eval(host, "luxnix.storage.operatorUnlocked.volumes")
            if not mutating:
                status = controller.tool("status")
                if args.action == "adopt":
                    status["plans"] = [controller.adopt(name, volumes[name], apply=False)
                                       for name in (args.volume or sorted(volumes))]
                elif args.action == "rollout":
                    status = controller.rollout(dict(sorted(volumes.items())),
                                                None, cutover=args.cutover, migration_enabled=nix_eval(
                                                    host, "luxnix.storage.operatorUnlocked.migration.enable"))
                status["escrow"] = {item: escrow_path(args.vault_dir, host, item).exists()
                                    for item in ("seal-key", "enrollment")}
                print(json.dumps(dict(status, action=args.action, apply=False), sort_keys=True))
                continue
            if args.action == "enroll":
                result = controller.enroll()
            elif args.action == "rotate-unlock":
                result = controller.rotate_unlock()
            elif args.action == "rollout":
                from lx_administration.storage.provision import main as provision_volume
                def provision_missing(name):
                    options = ['provision', '--host', host, '--volume', name,
                               '--backend', 'local-openbao', '--recovery-host', args.recovery_host,
                               '--vault-dir', str(args.vault_dir), '--vault-key', str(args.vault_key), '--apply']
                    if args.sudo_password_file:
                        options += ['--sudo-password-file', str(args.sudo_password_file)]
                    provision_volume(options)
                result = controller.rollout(dict(sorted(volumes.items())),
                                            provision_missing, apply=True, cutover=args.cutover,
                                            migration_enabled=nix_eval(host, "luxnix.storage.operatorUnlocked.migration.enable"))
            else:
                result = {"host": host, "volumes": [
                    controller.adopt(name, volumes[name], apply=True)
                    for name in (args.volume or sorted(volumes))]}
            print(json.dumps(result, sort_keys=True))
        except (EnrollmentError, ProvisionError, OSError, ValueError, KeyError,
                subprocess.SubprocessError) as exc:
            detail = str(exc) if isinstance(exc, (EnrollmentError, ProvisionError)) else type(exc).__name__
            print(f"ERROR: {host}: local OpenBao {args.action} blocked: {detail}", file=sys.stderr)
            failures += 1
            if mutating:
                break  # A wave stops at the first failed host.
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (EnrollmentError, ProvisionError, OSError, ValueError) as exc:
        detail = str(exc) if isinstance(exc, (EnrollmentError, ProvisionError)) else type(exc).__name__
        print(f"ERROR: local OpenBao enrollment blocked: {detail}", file=sys.stderr)
        sys.exit(1)
