"""Host side of local OpenBao enrollment, volume adoption and credential rotation.

Driven by the controller (local_enrollment.py) over SSH. Secrets arrive as JSON
on stdin and leave only as JSON on stdout for immediate escrow; never in argv or
logs. Every phase is idempotent: a rerun resumes, and nothing that exists is
replaced. Runs from the store with ``python3 -I``; the local client module is
loaded by path.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import runpy
import secrets
import subprocess
import sys
import time

BOOT = Path("/var/lib/openbao-bootstrap")
RAFT = Path("/var/lib/openbao-local/raft/raft.db")
SEAL = BOOT / "seal.cred"
UNLOCK = BOOT / "volume-unlock.cred"
# Root token and recovery key between initialization and confirmed escrow.
PENDING = BOOT / "pending-enrollment.cred"
# The provisioner SecretID issued for escrow; reused on resume so escrow is stable.
PENDING_PROVISIONER = BOOT / "pending-provisioner.cred"
LOCK = Path("/run/lock/luxnix-operator-migration")
TOKEN_TYPE = "luxnix-openbao"
UNLOCK_ROLE = "volume-unlock"
PROVISIONER_ROLE = "volume-provisioner"
NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class EnrollError(RuntimeError):
    """Operator-safe diagnostic without secret values."""


def run(*args, data: bytes | None = None, pass_fds=()) -> bytes:
    result = subprocess.run(
        [str(a) for a in args], input=data, capture_output=True, pass_fds=pass_fds, check=False
    )
    if result.returncode:
        raise EnrollError(f"{Path(str(args[0])).name} {args[1] if len(args) > 1 else ''} failed")
    return result.stdout


def pipe(secret: bytes) -> int:
    """Return a readable fd carrying secret, for tools that need two key files."""
    read, write = os.pipe()
    os.write(write, secret)
    os.close(write)
    return read


def seal_credential(name: str, plaintext: bytes, target: Path) -> None:
    """TPM-only, PCR 7; written atomically and never replaced."""
    BOOT.mkdir(mode=0o700, exist_ok=True)
    temporary = target.with_suffix(".new")
    temporary.unlink(missing_ok=True)
    run("systemd-creds", "encrypt", "--with-key=tpm2", "--tpm2-pcrs=7", f"--name={name}",
        "-", temporary, data=plaintext)
    os.chmod(temporary, 0o600)
    os.link(temporary, target)
    temporary.unlink()


def unseal_credential(name: str, source: Path) -> bytes:
    return run("systemd-creds", "decrypt", f"--name={name}", source, "-")


def escrow_digest(escrow: dict) -> str:
    """Binds confirmation to exactly the material the controller escrowed."""
    return hashlib.sha256(json.dumps(escrow, sort_keys=True).encode()).hexdigest()


class Host:
    def __init__(self, hostname: str, client: dict):
        if not NAME.fullmatch(hostname):
            raise EnrollError("Invalid inventory host name")
        self.hostname = hostname
        self.client = client

    def api(self, method, path, data=None, token=None):
        try:
            return self.client["call"](method, path, data, token, timeout=60)
        except self.client["DeniedError"] as exc:
            raise EnrollError(str(exc)) from None
        except (OSError, http.client.HTTPException):
            raise EnrollError(f"bao-unavailable: local OpenBao {path.split('/')[0]} unreachable") from None

    def wait_unsealed(self) -> None:
        try:
            self.client["wait_unsealed"](60)
        except ValueError as exc:
            raise EnrollError(f"bao-sealed: {exc}") from None

    def seal_status(self) -> dict:
        """Wait for the socket only; an uninitialized store is a valid answer."""
        for _ in range(240):
            try:
                return self.client["call"]("GET", "sys/seal-status", timeout=5)
            except (OSError, http.client.HTTPException):
                time.sleep(0.25)
        raise EnrollError("bao-unavailable: local OpenBao socket did not appear")

    # Status and preflight -------------------------------------------------

    def status(self) -> dict:
        return {
            "host": self.hostname,
            **self.client["platform_status"](),
            "seal_credential": SEAL.is_file(),
            "unlock_credential": UNLOCK.is_file(),
            "initialized": RAFT.is_file(),
            "pending_escrow": PENDING.is_file(),
            "enrolled": RAFT.is_file() and UNLOCK.is_file() and not PENDING.exists(),
        }

    def preflight(self) -> dict:
        """Live checks on every mutating phase; inventory assertions are not enough."""
        try:
            self.client["platform_preflight"]()
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            detail = (str(exc) if isinstance(exc, ValueError)
                      else "platform-check-failed")
            raise EnrollError(detail) from None
        return self.status()

    # Enrollment -------------------------------------------------------------

    def seal(self, request: dict) -> dict:
        self.preflight()
        key = base64.b64decode(request["seal_key"], validate=True)
        if len(key) != 32:
            raise EnrollError("Seal key must contain 32 bytes")
        if SEAL.exists():
            if not secrets.compare_digest(unseal_credential("seal.key", SEAL), key):
                raise EnrollError("Existing seal credential holds a different key; never replaced")
        elif RAFT.exists():
            raise EnrollError("A local store exists without its seal credential; use recovery, not enrollment")
        else:
            seal_credential("seal.key", key, SEAL)
        return {"sealed": True}

    def initialize(self) -> dict:
        self.preflight()
        if not SEAL.is_file():
            raise EnrollError("Seal credential missing; run the seal phase first")
        if PENDING.is_file():
            pending = json.loads(unseal_credential("pending.json", PENDING))
            self._start("openbao-local.service")
        elif RAFT.exists() and UNLOCK.exists():
            raise EnrollError("Store is initialized and escrow is confirmed; enrollment never reinitializes")
        else:
            if RAFT.exists():
                self._start("openbao-local.service")
            else:
                self._start("openbao-local-initialize.service")
            if self.seal_status().get("initialized") is not False:
                # Interrupted between sys/init and the pending credential: the store's
                # recovery key was never escrowed. Only an operator may discard it.
                raise EnrollError("interrupted-initialization: unescrowed store; see docs/openbao-local.md")
            response = self.api("POST", "sys/init", {"recovery_shares": 1, "recovery_threshold": 1})
            pending = {"root_token": response["root_token"],
                       "recovery_key": response["recovery_keys_base64"][0]}
            seal_credential("pending.json", json.dumps(pending).encode(), PENDING)
            self._stop("openbao-local-initialize.service")
            self._start("openbao-local.service")
        self.wait_unsealed()
        provisioner = self._configure(pending["root_token"])
        return {"escrow": {"recovery_key": pending["recovery_key"], "provisioner": provisioner}}

    def _configure(self, token: str) -> dict:
        mounts = self.api("GET", "sys/mounts", token=token).get("data", {})
        if "volume-release/" not in mounts:
            self.api("POST", "sys/mounts/volume-release",
                     {"type": "kv", "options": {"version": "2"}}, token)
        for _ in range(120):
            try:
                self.api("POST", "volume-release/config", {"cas_required": True}, token)
                break
            except EnrollError:
                time.sleep(0.5)
        else:
            raise EnrollError("KV v2 mount did not become ready")
        if "approle/" not in self.api("GET", "sys/auth", token=token).get("data", {}):
            self.api("POST", "sys/auth/approle", {"type": "approle"}, token)
        records = f"volume-release/data/{self.hostname}/*"
        role = f"auth/approle/role/{UNLOCK_ROLE}"
        policies = {
            UNLOCK_ROLE: f'path "{records}" {{ capabilities = ["read"] }}',
            PROVISIONER_ROLE: "\n".join([
                # cas_required on the mount makes every write create-only (cas=0).
                f'path "{records}" {{ capabilities = ["create", "read"] }}',
                f'path "volume-release/metadata/{self.hostname}/*" {{ capabilities = ["read", "list"] }}',
                f'path "{role}/secret-id" {{ capabilities = ["update", "list"] }}',
                f'path "{role}/secret-id-accessor/destroy" {{ capabilities = ["update"] }}',
                f'path "{role}/role-id" {{ capabilities = ["read"] }}',
            ]),
        }
        for name, policy in policies.items():
            self.api("PUT", f"sys/policies/acl/{name}", {"policy": policy}, token)
        common = {"secret_id_ttl": 0, "secret_id_num_uses": 0, "bind_secret_id": True,
                  "token_type": "service"}
        # Boot tokens live for one unlock only; the TPM-sealed SecretID never expires.
        self.api("POST", role, dict(common, token_policies=[UNLOCK_ROLE],
                                     token_ttl="60s", token_max_ttl="120s"), token)
        self.api("POST", f"auth/approle/role/{PROVISIONER_ROLE}",
                 dict(common, token_policies=[PROVISIONER_ROLE],
                      token_ttl="15m", token_max_ttl="30m"), token)
        if not UNLOCK.exists():
            seal_credential("volume.unlock", self._issue(UNLOCK_ROLE, token), UNLOCK)
        if not PENDING_PROVISIONER.exists():
            seal_credential("provisioner.json", self._issue(PROVISIONER_ROLE, token),
                            PENDING_PROVISIONER)
        return json.loads(unseal_credential("provisioner.json", PENDING_PROVISIONER))

    def _issue(self, role: str, token: str) -> bytes:
        role_id = self.api("GET", f"auth/approle/role/{role}/role-id", token=token)["data"]["role_id"]
        issued = self.api("POST", f"auth/approle/role/{role}/secret-id", {}, token)["data"]
        return json.dumps({"role_id": role_id, "secret_id": issued["secret_id"],
                           "accessor": issued["secret_id_accessor"]}).encode()

    def _destroy_except(self, role: str, keep: str, token: str) -> None:
        """Remove SecretIDs orphaned by interrupted runs; exactly one stays valid."""
        path = f"auth/approle/role/{role}/secret-id"
        try:
            accessors = self.api("LIST", path, token=token).get("data", {}).get("keys", [])
        except EnrollError:
            accessors = []  # OpenBao answers 404 for an empty list.
        for accessor in accessors:
            if accessor != keep:
                self.api("POST", f"auth/approle/role/{role}/secret-id-accessor/destroy",
                         {"secret_id_accessor": accessor}, token)

    def confirm(self, request: dict) -> dict:
        self.preflight()
        if not PENDING.is_file() or not PENDING_PROVISIONER.is_file():
            raise EnrollError("No pending enrollment")
        pending = json.loads(unseal_credential("pending.json", PENDING))
        provisioner = json.loads(unseal_credential("provisioner.json", PENDING_PROVISIONER))
        escrow = {"recovery_key": pending["recovery_key"], "provisioner": provisioner}
        # Proves the controller escrowed exactly this material before the root token goes.
        if not secrets.compare_digest(str(request.get("escrow_sha256", "")), escrow_digest(escrow)):
            raise EnrollError("Escrowed material does not match this store")
        self.wait_unsealed()
        unlock = json.loads(unseal_credential("volume.unlock", UNLOCK))
        try:
            probe = self.client["login"](json.dumps(unlock).encode())
        except ValueError as exc:
            raise EnrollError(f"unlock-credential-rejected: {exc}") from None
        self.api("POST", "auth/token/revoke-self", {}, probe)
        token = pending["root_token"]
        try:
            self.api("GET", "auth/token/lookup-self", token=token)
            alive = True
        except EnrollError:
            alive = False  # Revoked by an interrupted earlier confirmation.
        if alive:
            self._destroy_except(UNLOCK_ROLE, unlock["accessor"], token)
            self._destroy_except(PROVISIONER_ROLE, provisioner["accessor"], token)
            self.api("POST", "auth/token/revoke-self", {}, token)
        PENDING_PROVISIONER.unlink()
        PENDING.unlink()
        return {"confirmed": True, "root_token_revoked": True}

    # Volume adoption -------------------------------------------------------

    def _login(self, credential: dict) -> str:
        try:
            return self.client["login"](json.dumps(credential).encode())
        except ValueError as exc:
            raise EnrollError(f"provisioner-rejected: {exc}") from None

    def _volume(self, name: str, container: str, luks_uuid: str) -> Path:
        if not NAME.fullmatch(name or "") or not UUID.fullmatch(luks_uuid or ""):
            raise EnrollError("Invalid volume identity")
        path = Path(container or "")
        if not path.is_absolute() or path.resolve() != path or not path.is_file():
            raise EnrollError("volume-missing: declared container is absent; adoption never provisions")
        if run("cryptsetup", "luksUUID", path).decode().strip() != luks_uuid:
            raise EnrollError("Native LUKS UUID does not match the declared volume")
        return path

    def plan_volume(self, name: str, container: str, luks_uuid: str) -> dict:
        """Read-only keyslot and token plan shown before any adoption."""
        metadata = _metadata(self._volume(name, container, luks_uuid))
        tokens = metadata.get("tokens", {})
        openbao = _openbao_slot(metadata)
        changes = [] if openbao is not None else ["add OpenBao keyslot and luxnix-openbao token"]
        for token_id, token in sorted(tokens.items()):
            if token.get("type") == "systemd-tpm2":
                changes.append(f"remove systemd-tpm2 token {token_id} and keyslots "
                               f"{','.join(token.get('keyslots', []))}")
        return {
            "volume": name,
            "luks_uuid": luks_uuid,
            "keyslots": sorted(metadata.get("keyslots", {})),
            "tokens": {key: {"type": token.get("type"), "keyslots": token.get("keyslots", [])}
                       for key, token in sorted(tokens.items())},
            "openbao_keyslot": openbao,
            "changes": changes,
        }

    def volume_record(self, name: str, luks_uuid: str, credential: dict, container: str | None = None) -> bytes:
        """Create/read the UUID-bound secret before allocating a new container."""
        if not NAME.fullmatch(name or "") or not UUID.fullmatch(luks_uuid or ""):
            raise EnrollError("Invalid volume identity")
        self.preflight()
        if not RAFT.exists() or not UNLOCK.exists() or PENDING.exists():
            raise EnrollError("Enrollment must be complete before provisioning volumes")
        enrolled = container is not None and _openbao_slot(_metadata(self._volume(name, container, luks_uuid))) is not None
        self.wait_unsealed()
        token = self._login(credential)
        record = f"volume-release/data/{self.hostname}/{name}/{luks_uuid}"
        try:
            try:
                stored = self.api("GET", record, token=token)["data"]["data"]
            except EnrollError:
                if enrolled:
                    raise EnrollError("record-missing: restore the enrolled volume secret; never replace it") from None
                key = secrets.token_bytes(32)
                self.api("POST", record, {"options": {"cas": 0}, "data": {
                    "key": base64.b64encode(key).decode(), "luks_uuid": luks_uuid}}, token)
                stored = self.api("GET", record, token=token)["data"]["data"]
            key = base64.b64decode(stored["key"], validate=True)
            if len(key) != 32 or stored["luks_uuid"] != luks_uuid:
                raise EnrollError("record-mismatch: stored record does not match the volume")
        finally:
            self.api("POST", "auth/token/revoke-self", {}, token)
        return key

    def convert_volume(self, name: str, container: str, luks_uuid: str, request: dict) -> dict:
        """Add an OpenBao keyslot to an existing container and remove systemd-tpm2 tokens."""
        self.preflight()
        if not RAFT.exists() or not UNLOCK.exists() or PENDING.exists():
            raise EnrollError("Enrollment must be complete before adopting volumes")
        path = self._volume(name, container, luks_uuid)
        recovery = request["recovery_passphrase"].encode()
        recovery_slot = _slot_for(path, recovery)
        if recovery_slot is None:
            raise EnrollError("recovery-passphrase-rejected")
        key = self.volume_record(name, luks_uuid, request["provisioner"], container)
        record = f"volume-release/data/{self.hostname}/{name}/{luks_uuid}"
        # Identify the slot by test-open, so an interrupted luksAddKey is never repeated.
        slot = _slot_for(path, key)
        if slot is None:
            existing, new = pipe(recovery), pipe(key)
            try:
                run("cryptsetup", "luksAddKey", "--batch-mode", f"--key-file=/dev/fd/{existing}",
                    path, f"/dev/fd/{new}", pass_fds=(existing, new))
            finally:
                os.close(existing)
                os.close(new)
            slot = _slot_for(path, key)
            if slot is None:
                raise EnrollError("keyslot-rejected: the new OpenBao keyslot does not open")
        if slot == recovery_slot:
            raise EnrollError("OpenBao key and recovery passphrase share a keyslot")
        metadata = _metadata(path)
        marked = _openbao_slot(metadata)
        if marked not in (None, slot):
            raise EnrollError("A luxnix-openbao token references a different keyslot")
        if marked is None:
            run("cryptsetup", "token", "import", "--json-file=-", path, data=json.dumps({
                "type": TOKEN_TYPE, "keyslots": [slot], "record": record}).encode())
        removed = self._remove_tpm2_tokens(path, recovery, {slot, recovery_slot})
        if _slot_for(path, key) != slot or _slot_for(path, recovery) != recovery_slot:
            raise EnrollError("keyslot-rejected: post-adoption test-open failed")
        mapping = request.get("open_mapping")
        if mapping is not None:
            if not NAME.fullmatch(mapping):
                raise EnrollError("Invalid rollout mapping name")
            if Path("/dev/mapper", mapping).exists():
                status = run("cryptsetup", "status", mapping).decode()
                fields = dict(line.strip().split(":", 1) for line in status.splitlines() if ":" in line)
                if fields.get("loop", "").strip() != str(path):
                    raise EnrollError("Rollout mapping belongs to another container")
            else:
                run("cryptsetup", "open", "--type", "luks", "--key-file=-", path, mapping, data=key)
        return {"volume": name, "openbao_keyslot": slot, "recovery_keyslot": recovery_slot,
                "removed_tpm2_keyslots": removed}

    def _remove_tpm2_tokens(self, path: Path, recovery: bytes, protected: set[str]) -> list[str]:
        removed = []
        for token_id, token in sorted(_metadata(path).get("tokens", {}).items()):
            if token.get("type") != "systemd-tpm2":
                continue
            slots = token.get("keyslots", [])
            if protected & set(slots):
                raise EnrollError("A systemd-tpm2 token shares a protected keyslot; not removed")
            for slot in slots:
                fd = pipe(recovery)
                try:
                    run("cryptsetup", "luksKillSlot", "--batch-mode", f"--key-file=/dev/fd/{fd}",
                        path, slot, pass_fds=(fd,))
                finally:
                    os.close(fd)
                removed.append(slot)
            if token_id in _metadata(path).get("tokens", {}):
                run("cryptsetup", "token", "remove", "--token-id", token_id, path)
        return removed

    # Credential lifecycle --------------------------------------------------

    def rotate_unlock(self, request: dict) -> dict:
        """Replace the boot SecretID; the old one is destroyed only after the new one works."""
        self.preflight()
        self.wait_unsealed()
        old = json.loads(unseal_credential("volume.unlock", UNLOCK))
        token = self._login(request["provisioner"])
        try:
            role = f"auth/approle/role/{UNLOCK_ROLE}"
            issued = self.api("POST", f"{role}/secret-id", {}, token)["data"]
            new = {"role_id": old["role_id"], "secret_id": issued["secret_id"],
                   "accessor": issued["secret_id_accessor"]}
            replacement = UNLOCK.with_name("volume-unlock.rotating")
            replacement.unlink(missing_ok=True)
            seal_credential("volume.unlock", json.dumps(new).encode(), replacement)
            probe = self._login(new)
            self.api("POST", "auth/token/revoke-self", {}, probe)
            os.replace(replacement, UNLOCK)
            self._destroy_except(UNLOCK_ROLE, new["accessor"], token)
        finally:
            self.api("POST", "auth/token/revoke-self", {}, token)
        return {"rotated": True}

    # Units -------------------------------------------------------------------

    def _start(self, unit: str) -> None:
        run("systemctl", "start", unit)

    def _stop(self, unit: str) -> None:
        run("systemctl", "stop", unit)


def _metadata(path: Path) -> dict:
    return json.loads(run("cryptsetup", "luksDump", "--dump-json-metadata", path))


def _openbao_slot(metadata: dict) -> str | None:
    for token in metadata.get("tokens", {}).values():
        if token.get("type") == TOKEN_TYPE:
            return token["keyslots"][0]
    return None


def _slot_for(path: Path, key: bytes) -> str | None:
    """The keyslot a secret opens, or None; never activates a mapping."""
    result = subprocess.run(
        ["cryptsetup", "open", "--test-passphrase", "--verbose", "--key-file=-", str(path)],
        input=key, capture_output=True, check=False,
    )
    match = re.search(rb"Key slot (\d+) unlocked", result.stdout + result.stderr)
    return match.group(1).decode() if result.returncode == 0 and match else None


MUTATING = {"seal", "initialize", "confirm", "convert-volume", "rotate-unlock"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("command", choices=["status", "preflight", "plan-volume", *sorted(MUTATING)])
    parser.add_argument("--volume")
    parser.add_argument("--container")
    parser.add_argument("--luks-uuid")
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if os.geteuid() != 0:
            raise EnrollError("Run as root")
        host = Host(args.hostname, runpy.run_path(str(args.client)))
        request = json.loads(sys.stdin.buffer.read(65536) or b"{}") if args.command in {
            "seal", "confirm", "convert-volume", "rotate-unlock"} else {}
        LOCK.parent.mkdir(mode=0o755, exist_ok=True)
        with open(LOCK, "a") as lock:
            if args.command in MUTATING:
                # Shared with operator_migration.py: one mutation per host at a time.
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise EnrollError("conflict: another storage mutation is running") from None
            if args.command == "status":
                result = host.status()
            elif args.command == "preflight":
                result = host.preflight()
            elif args.command == "plan-volume":
                result = host.plan_volume(args.volume, args.container, args.luks_uuid)
            elif args.command == "seal":
                result = host.seal(request)
            elif args.command == "initialize":
                result = host.initialize()
            elif args.command == "confirm":
                result = host.confirm(request)
            elif args.command == "convert-volume":
                result = host.convert_volume(args.volume, args.container, args.luks_uuid, request)
            else:
                result = host.rotate_unlock(request)
    except (EnrollError, KeyError, ValueError, OSError, subprocess.SubprocessError) as exc:
        detail = str(exc) if isinstance(exc, EnrollError) else type(exc).__name__
        if isinstance(exc, KeyError) and exc.args and isinstance(exc.args[0], str) \
                and NAME.fullmatch(exc.args[0].replace("_", "-")):
            detail = f"missing field {exc.args[0]}"  # A schema name, never a value.
        print(f"ERROR: {detail}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
