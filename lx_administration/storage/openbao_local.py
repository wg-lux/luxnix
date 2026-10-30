"""Validate local OpenBao bootstrap without initializing or replacing state.

The credential header is a policy filter, not authentication: systemd must still
unseal and authenticate it. Unknown formats fail closed (systemd v260 layout).
"""

import argparse
import base64
import hashlib
import hmac
import http.client
import json
import re
import secrets
import socket
import time
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys

TPM_ONLY = bytes.fromhex("0c7cc07b117645919c4b0bea08bc20fe")
SOCKET = "/run/openbao-local/api.sock"
# Passphrase seal: the escrowed seal key is stored wrapped by the boot passphrase
# and staged on tmpfs only after the operator answered the boot prompt.
SEAL_WRAP = Path("/var/lib/openbao-bootstrap/seal-passphrase.json")
SEAL_RUNTIME = Path("/run/luxnix-openbao-seal/seal.key")
SCRYPT = {"n": 2**17, "r": 8, "p": 1}
MIN_PASSPHRASE = 12
PASSPHRASE_ATTEMPTS = 5
SECURE_BOOT = Path(
    "/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"
)
TPM = Path("/sys/class/tpm/tpm0")


def platform_status() -> dict:
    """Read live prerequisites, never infer them from inventory declarations.

    Known virtualization and non-platform drivers are rejected. This is not
    remote attestation or proof against a hypervisor that conceals itself.
    """
    tpm = subprocess.run(["systemd-creds", "has-tpm2"], capture_output=True, timeout=15)
    virtual = subprocess.run(["systemd-detect-virt"], capture_output=True, timeout=15)
    try:
        secure_boot = SECURE_BOOT.read_bytes()[4:] == b"\x01"
    except OSError:
        secure_boot = False
    try:
        physical = (
            virtual.returncode == 1 and virtual.stdout.strip() == b"none"
            and (TPM / "tpm_version_major").read_text().strip() == "2"
            and (TPM / "device/driver").resolve(strict=True).name
            in {"tpm_crb", "tpm_tis"}
        )
    except OSError:
        physical = False
    return {"tpm2": tpm.returncode == 0, "physical_tpm": physical,
            "secure_boot": secure_boot, "secure_boot_required": True}


def platform_preflight() -> dict:
    status = platform_status()
    if not status["tpm2"]:
        raise ValueError("tpm-missing: no usable TPM 2.0; no fallback")
    if not status["physical_tpm"]:
        raise ValueError("tpm-not-physical: virtualized or unrecognized TPM platform")
    if not status["secure_boot"]:
        raise ValueError("secure-boot-disabled: firmware Secure Boot is required")
    return status


class DeniedError(RuntimeError):
    """An API refusal; distinct from a socket that is not ready yet."""


def validate_credential(blob: bytes) -> None:
    data = base64.b64decode(b"".join(blob.split()), validate=True)
    if len(data) < 80 or data[:16] != TPM_ONLY:
        raise ValueError("Credential must use explicit --with-key=tpm2")
    key_size, block_size, iv_size, tag_size = struct.unpack_from("<IIII", data, 16)
    if (key_size, block_size, iv_size, tag_size) != (32, 1, 12, 16):
        raise ValueError("Unsupported encrypted credential header")
    offset = (32 + iv_size + 7) & ~7
    mask = struct.unpack_from("<Q", data, offset)[0]
    if not mask & (1 << 7) or mask >> 24:
        raise ValueError("TPM credential must bind PCR 7")


def read_private(path: Path) -> bytes:
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("Bootstrap path must be absolute without symlinks")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise ValueError("Bootstrap file must be a root-owned private regular file")
        data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Bootstrap file exceeds size limit")
        return data


def preflight(credential: Path, seal: str = "tpm") -> None:
    data = read_private(credential)
    # A passphrase-sealed store protects its AppRole credential through the seal:
    # without the boot passphrase the credential cannot reach any record.
    if seal == "tpm":
        validate_credential(data)


def key_check(key: bytes) -> str:
    return hashlib.sha256(b"luxnix-openbao-seal-check-v1" + key).hexdigest()


def _kek(passphrase: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(passphrase, salt=salt, maxmem=2**28, dklen=64, **SCRYPT)


def wrap_seal_key(key: bytes, passphrase: bytes) -> dict:
    """Encrypt-then-MAC with a fresh salt, so each pad is used exactly once."""
    if len(key) != 32:
        raise ValueError("Seal key must contain 32 bytes")
    if len(passphrase) < MIN_PASSPHRASE:
        raise ValueError(f"Boot passphrase must contain at least {MIN_PASSPHRASE} characters")
    salt = secrets.token_bytes(32)
    kek = _kek(passphrase, salt)
    pad = hmac.new(kek[:32], b"luxnix-openbao-seal-wrap-v1", hashlib.sha256).digest()
    wrapped = bytes(a ^ b for a, b in zip(key, pad))
    tag = hmac.new(kek[32:], salt + wrapped, hashlib.sha256).digest()
    encode = lambda value: base64.b64encode(value).decode()
    return {"version": 1, "kdf": "scrypt", **SCRYPT, "salt": encode(salt),
            "wrapped": encode(wrapped), "tag": encode(tag), "key_check": key_check(key)}


def validate_seal_record(record: dict) -> None:
    # Fixed parameters: a tampered record cannot select a cheaper or exhausting KDF.
    if not isinstance(record, dict) or record.get("version") != 1 or record.get("kdf") != "scrypt" or any(
            record.get(name) != value for name, value in SCRYPT.items()):
        raise ValueError("Unsupported seal passphrase record")
    try:
        if any(len(base64.b64decode(record[name], validate=True)) != 32
               for name in ("salt", "wrapped", "tag")) or not re.fullmatch(r"[0-9a-f]{64}", record["key_check"]):
            raise ValueError("Invalid seal passphrase record")
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid seal passphrase record") from exc


def unwrap_seal_key(record: dict, passphrase: bytes) -> bytes:
    validate_seal_record(record)
    salt = base64.b64decode(record["salt"], validate=True)
    wrapped = base64.b64decode(record["wrapped"], validate=True)
    kek = _kek(passphrase, salt)
    tag = hmac.new(kek[32:], salt + wrapped, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, base64.b64decode(record["tag"], validate=True)):
        raise ValueError("wrong-passphrase")
    pad = hmac.new(kek[:32], b"luxnix-openbao-seal-wrap-v1", hashlib.sha256).digest()
    key = bytes(a ^ b for a, b in zip(wrapped, pad))
    if len(key) != 32 or not hmac.compare_digest(key_check(key), record["key_check"]):
        raise ValueError("Seal passphrase record is inconsistent")
    return key


def write_private(path: Path, data: bytes) -> None:
    """Create a root-only file atomically; never follows or replaces a symlink."""
    path.parent.mkdir(mode=0o700, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def seal_receipt(record: dict, key: bytes) -> bytes:
    return hmac.digest(key, json.dumps(record, sort_keys=True).encode(), "sha256")


def stage_verified_seal(record: dict, key: bytes, target=SEAL_RUNTIME) -> None:
    """Called only after wrapping or authenticating this exact record and key."""
    if target.exists() and not hmac.compare_digest(read_private(target), key):
        raise ValueError("Staged seal key does not match this store")
    write_private(target, key)
    write_private(target.with_suffix(".receipt"), seal_receipt(record, key))


def verify_staged_seal(record_path=SEAL_WRAP, target=SEAL_RUNTIME) -> None:
    record = json.loads(read_private(record_path))
    validate_seal_record(record)
    key = read_private(target)
    if len(key) != 32 or not hmac.compare_digest(key_check(key), record["key_check"]):
        raise ValueError("Staged seal key does not match this store")
    if not hmac.compare_digest(read_private(target.with_suffix(".receipt")), seal_receipt(record, key)):
        raise ValueError("Seal record was not authenticated at this boot; rerun the seal phase")


def stage_seal_key(record_path=SEAL_WRAP, target=SEAL_RUNTIME, attempts=PASSPHRASE_ATTEMPTS):
    """Boot prompt: verify the passphrase, then stage the seal key on tmpfs."""
    record = json.loads(read_private(record_path))
    validate_seal_record(record)
    if target.exists():
        # An OpenBao restart reuses the key verified at this boot.
        verify_staged_seal(record_path, target)
        return
    for _ in range(attempts):
        passphrase = subprocess.run(
            ["systemd-ask-password", "--timeout=0", "Unlock local OpenBao:"],
            capture_output=True, check=True, timeout=None,
        ).stdout.rstrip(b"\n")
        try:
            key = unwrap_seal_key(record, passphrase)
        except ValueError:
            continue
        stage_verified_seal(record, key, target)
        return
    raise ValueError(f"No valid boot passphrase after {attempts} attempts")


class LocalConnection(http.client.HTTPConnection):
    def __init__(self, path=SOCKET, timeout=5):
        super().__init__("localhost", timeout=timeout)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def call(method, path, data=None, token=None, socket_path=SOCKET, timeout=5):
    """One API call over the private socket; bodies are never logged."""
    connection = LocalConnection(socket_path, timeout=timeout)
    try:
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Vault-Token"] = token
        body = None if data is None else json.dumps(data)
        connection.request(method, "/v1/" + path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read(65537)
        if path == "sys/health" and response.status in (429, 503):
            raise BlockingIOError("Local OpenBao is not active yet")
        if response.status not in (200, 204) or len(raw) > 65536:
            raise DeniedError(f"Local OpenBao {method} {path.split('/')[0]} denied or unavailable")
        return json.loads(raw) if raw else {}
    finally:
        connection.close()


def request(path, token=None, socket_path=SOCKET):
    try:
        return call("GET", path, token=token, socket_path=socket_path)
    except DeniedError as exc:
        raise ValueError(str(exc)) from exc


def wait_unsealed(timeout, socket_path=SOCKET):
    """Unsealed and active, not merely a running service."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            status = request("sys/seal-status", socket_path=socket_path)
            if status.get("initialized") is not True:
                raise ValueError("Local OpenBao is not initialized")
            if status.get("sealed") is False:
                request("sys/health", socket_path=socket_path)
                return
        except (OSError, http.client.HTTPException):
            pass
        if time.monotonic() >= deadline:
            raise ValueError("Local OpenBao unseal deadline exceeded")
        time.sleep(0.2)


def login(credential, socket_path=SOCKET):
    """Exchange the TPM-sealed AppRole credential for a short-lived token."""
    try:
        values = json.loads(credential)
        role_id, secret_id = values["role_id"], values["secret_id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Invalid local OpenBao unlock credential") from exc
    for value in (role_id, secret_id):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9-]+", value):
            raise ValueError("Invalid local OpenBao unlock credential")
    try:
        response = call(
            "POST", "auth/approle/login", {"role_id": role_id, "secret_id": secret_id},
            socket_path=socket_path,
        )
        token = response["auth"]["client_token"]
    except (DeniedError, KeyError, TypeError) as exc:
        raise ValueError("Local OpenBao rejected the unlock credential") from exc
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", token):
        raise ValueError("Invalid local OpenBao token")
    return token


def volume_key(machine, volume, luks_uuid, credential_file, timeout=60, socket_path=SOCKET):
    for part in (machine, volume, luks_uuid):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", part):
            raise ValueError("Invalid local OpenBao record identity")
    credential = read_private(Path(credential_file))
    wait_unsealed(timeout, socket_path)
    token = login(credential, socket_path)
    # No retries on a denied, missing or malformed key; no fallback provider.
    try:
        record = call("GET", f"volume-release/data/{machine}/{volume}/{luks_uuid}",
                      token=token, socket_path=socket_path)
        data = record["data"]["data"]
        if data["luks_uuid"] != luks_uuid:
            raise ValueError("Local OpenBao record UUID mismatch")
        key = base64.b64decode(data["key"], validate=True)
        if len(key) != 32:
            raise ValueError("Local OpenBao key must contain 32 bytes")
        return key
    except (
        DeniedError,
        KeyError,
        TypeError,
        UnicodeError,
        OSError,
        http.client.HTTPException,
    ) as exc:
        raise ValueError("Invalid local OpenBao volume response") from exc
    finally:
        # The token is single-purpose; never leave it valid after the read.
        try:
            call("POST", "auth/token/revoke-self", token=token, socket_path=socket_path)
        except (DeniedError, OSError, http.client.HTTPException):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("credential", type=Path, nargs="?")
    parser.add_argument("--platform-only", action="store_true")
    parser.add_argument("--stage-seal", action="store_true")
    parser.add_argument("--verify-seal", action="store_true")
    parser.add_argument("--seal", choices=["tpm", "passphrase"], default="tpm")
    args = parser.parse_args()
    try:
        if args.platform_only:
            platform_preflight()
        elif args.stage_seal:
            stage_seal_key()
        elif args.verify_seal:
            verify_staged_seal()
            wait_unsealed(5)
        elif args.credential is not None:
            preflight(args.credential, args.seal)
        else:
            parser.error("credential, --stage-seal or --platform-only is required")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        if (args.platform_only or args.stage_seal) and isinstance(exc, ValueError):
            print(str(exc), file=sys.stderr)
        print("Local OpenBao bootstrap validation failed; no fallback", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
