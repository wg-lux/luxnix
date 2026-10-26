"""TPM-bound device identity and central volume release client (ENC-05/ENC-06).

The TLS client key is created inside the TPM below the TCG storage root key
(SRK) and never exists in plaintext. The TSS2 key file is a TPM-wrapped blob
that only loads in the TPM that created it, so a copy of the unencrypted root
disk does not carry a usable identity. Release responses go to stdout only;
tokens and volume secrets never appear in arguments, logs or error messages.

Exit codes distinguish failure classes for the unlock path (ENC-13).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

SRK_HANDLE = 0x81000001
TSS2_KEY_OID = "2.23.133.10.1.3"
SRK_ATTRIBUTES = "fixedtpm|fixedparent|sensitivedataorigin|userwithauth|restricted|decrypt|noda"
KEY_ATTRIBUTES = "fixedtpm|fixedparent|sensitivedataorigin|userwithauth|sign|noda"

# TPMA_OBJECT bits (TPM 2.0 Part 2, 8.3).
FIXED_TPM = 0x2
FIXED_PARENT = 0x10
SENSITIVE_DATA_ORIGIN = 0x20
RESTRICTED = 0x10000
DECRYPT = 0x20000
SIGN = 0x40000

# Host, volume and mount names become API path segments and certificate subjects.
SEGMENT = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}")

PROVIDERS = ("-provider", "tpm2", "-provider", "default")
CURL_TLS = ("--engine", "tpm2", "--key-type", "PROV")

EXIT_CONFIG = 2
EXIT_UNREACHABLE = 3
EXIT_DENIED = 4
EXIT_SEALED = 5
EXIT_NOT_FOUND = 6
EXIT_IDENTITY = 7


class ReleaseError(RuntimeError):
    def __init__(self, code: int, reason: str, message: str):
        super().__init__(message)
        self.code = code
        self.reason = reason


def run(*args: str, input: bytes | None = None) -> bytes:
    result = subprocess.run(args, input=input, capture_output=True, check=False)
    if result.returncode:
        # Tool diagnostics are not echoed; they may contain key material paths or payloads.
        raise ReleaseError(
            EXIT_IDENTITY, "tpm-tool-failed", f"{args[0]} failed (exit {result.returncode})"
        )
    return result.stdout


# Minimal DER for the TSS2 key file (TPM 2.0 Key File format, used by
# tpm2-openssl). Encoded here because tpm2_encodeobject 5.7 inverts emptyAuth.
def _der(tag: int, body: bytes) -> bytes:
    if len(body) < 0x80:
        length = bytes([len(body)])
    else:
        raw = len(body).to_bytes((len(body).bit_length() + 7) // 8, "big")
        length = bytes([0x80 | len(raw)]) + raw
    return bytes([tag]) + length + body


def _oid(dotted: str) -> bytes:
    first, second, *rest = (int(part) for part in dotted.split("."))
    body = bytearray([40 * first + second])
    for value in rest:
        chunk = [value & 0x7F]
        while value := value >> 7:
            chunk.append(0x80 | (value & 0x7F))
        body.extend(reversed(chunk))
    return _der(0x06, bytes(body))


def _integer(value: int) -> bytes:
    return _der(0x02, value.to_bytes(value.bit_length() // 8 + 1, "big"))


def _read_der(data: bytes, offset: int) -> tuple[int, bytes, int]:
    tag, length = data[offset], data[offset + 1]
    offset += 2
    if length & 0x80:
        size = length & 0x7F
        length = int.from_bytes(data[offset : offset + size], "big")
        offset += size
    end = offset + length
    if end > len(data):
        raise ReleaseError(EXIT_IDENTITY, "identity-malformed", "Truncated TSS2 key file")
    return tag, data[offset:end], end


def encode_tss2(public: bytes, private: bytes, parent: int = SRK_HANDLE) -> str:
    body = (
        _oid(TSS2_KEY_OID)
        + _der(0xA0, _der(0x01, b"\xff"))
        + _integer(parent)
        + _der(0x04, public)
        + _der(0x04, private)
    )
    encoded = base64.encodebytes(_der(0x30, body)).decode().replace("\n", "")
    lines = [encoded[i : i + 64] for i in range(0, len(encoded), 64)]
    return (
        "-----BEGIN TSS2 PRIVATE KEY-----\n"
        + "\n".join(lines)
        + "\n-----END TSS2 PRIVATE KEY-----\n"
    )


def decode_tss2(text: str) -> dict:
    begin, end = "-----BEGIN TSS2 PRIVATE KEY-----", "-----END TSS2 PRIVATE KEY-----"
    if begin not in text or end not in text:
        raise ReleaseError(
            EXIT_IDENTITY,
            "identity-not-tpm",
            "Key is not a TSS2 TPM-wrapped key; plaintext keys are rejected",
        )
    data = base64.b64decode(text.split(begin, 1)[1].split(end, 1)[0])
    tag, body, _ = _read_der(data, 0)
    fields, offset = [], 0
    while offset < len(body):
        field_tag, value, offset = _read_der(body, offset)
        fields.append((field_tag, value))
    if not fields or fields[0] != (0x06, _oid(TSS2_KEY_OID)[2:]):
        raise ReleaseError(EXIT_IDENTITY, "identity-not-tpm", "Unsupported TSS2 key type")
    # Writers differ in their TRUE encoding (0xff or 0x01); accept any non-zero BOOLEAN.
    empty_auth = any(
        tag == 0xA0 and value[:2] == b"\x01\x01" and value[2:3] not in (b"", b"\x00")
        for tag, value in fields
    )
    rest = [(tag, value) for tag, value in fields[1:] if tag != 0xA0]
    if [tag for tag, _ in rest] != [0x02, 0x04, 0x04]:
        raise ReleaseError(EXIT_IDENTITY, "identity-malformed", "Unexpected TSS2 key structure")
    public = rest[1][1]
    # TPM2B_PUBLIC: size(2) type(2) nameAlg(2) objectAttributes(4)
    attributes = int.from_bytes(public[6:10], "big")
    return {
        "parent": int.from_bytes(rest[0][1], "big"),
        "attributes": attributes,
        "empty_auth": empty_auth,
    }


def require_identity_attributes(info: dict) -> None:
    attributes = info["attributes"]
    required = FIXED_TPM | FIXED_PARENT | SENSITIVE_DATA_ORIGIN | SIGN
    if attributes & required != required:
        raise ReleaseError(
            EXIT_IDENTITY,
            "identity-exportable",
            "Key must be fixedTPM, fixedParent, TPM-generated and signing",
        )
    if attributes & (DECRYPT | RESTRICTED):
        raise ReleaseError(EXIT_IDENTITY, "identity-attributes", "Identity key must be sign-only")
    if info["parent"] != SRK_HANDLE:
        raise ReleaseError(
            EXIT_IDENTITY,
            "identity-parent",
            f"Identity key must be a child of the SRK {SRK_HANDLE:#x}",
        )
    if not info["empty_auth"]:
        raise ReleaseError(
            EXIT_IDENTITY, "identity-auth", "Unattended identity key must use empty auth"
        )


def require_segment(value: str, field: str) -> str:
    if not SEGMENT.fullmatch(value):
        raise ReleaseError(
            EXIT_CONFIG, "release-config", f"Invalid {field}: use lowercase letters, digits, - or _"
        )
    return value


def require_release_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment:
        raise ReleaseError(EXIT_CONFIG, "release-config", "Release URL must be a plain HTTPS URL")
    if parts.username or parts.password or any(ord(c) < 0x21 or ord(c) == 0x7F for c in url):
        raise ReleaseError(EXIT_CONFIG, "release-config", "Release URL must not embed credentials")
    return url.rstrip("/")


def _field(document: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(document, dict):
            return None
        document = document.get(key)
    return document


def _srk_present() -> bool:
    return (
        subprocess.run(
            ("tpm2_readpublic", "-c", hex(SRK_HANDLE)), capture_output=True, check=False
        ).returncode
        == 0
    )


def _require_srk(create: bool) -> None:
    if _srk_present():
        public = run("tpm2_readpublic", "-c", hex(SRK_HANDLE)).decode()
        if not all(flag in public for flag in ("fixedtpm", "fixedparent", "restricted", "decrypt")):
            raise ReleaseError(
                EXIT_IDENTITY,
                "srk-invalid",
                f"Persistent handle {SRK_HANDLE:#x} is not a storage root key",
            )
        return
    if not create:
        raise ReleaseError(
            EXIT_IDENTITY,
            "srk-missing",
            f"No SRK at {SRK_HANDLE:#x}; rerun with --create-srk to persist the TCG SRK",
        )
    with tempfile.TemporaryDirectory() as work:
        context = str(Path(work) / "srk.ctx")
        run(
            "tpm2_createprimary",
            "-Q",
            "-C",
            "o",
            "-g",
            "sha256",
            "-G",
            "ecc256:aes128cfb",
            "-a",
            SRK_ATTRIBUTES,
            "-c",
            context,
        )
        run("tpm2_evictcontrol", "-Q", "-C", "o", "-c", context, hex(SRK_HANDLE))
        # Without the kernel resource manager transient objects would stay loaded.
        run("tpm2_flushcontext", "-t")


def _write_new(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def identity_create(key: Path, csr: Path, name: str, create_srk: bool) -> None:
    require_segment(name, "name")
    if key.exists() or csr.exists():
        raise ReleaseError(
            EXIT_IDENTITY,
            "identity-exists",
            "Identity already exists; never regenerate an enrolled identity",
        )
    _require_srk(create_srk)
    with tempfile.TemporaryDirectory() as work:
        public, private = Path(work) / "key.pub", Path(work) / "key.priv"
        run(
            "tpm2_create",
            "-Q",
            "-C",
            hex(SRK_HANDLE),
            "-G",
            "ecc256",
            "-a",
            KEY_ATTRIBUTES,
            "-u",
            str(public),
            "-r",
            str(private),
        )
        run("tpm2_flushcontext", "-t")
        pem = encode_tss2(public.read_bytes(), private.read_bytes())
    require_identity_attributes(decode_tss2(pem))
    _write_new(key, pem.encode(), 0o600)
    request = run(
        "openssl",
        "req",
        *PROVIDERS,
        "-new",
        "-key",
        str(key),
        "-subj",
        f"/CN={name}",
        "-addext",
        "extendedKeyUsage=clientAuth",
    )
    _write_new(csr, request, 0o644)


def identity_check(key: Path, certificate: Path, name: str) -> None:
    require_segment(name, "name")
    require_identity_attributes(decode_tss2(key.read_text()))
    subject = run(
        "openssl", "x509", "-in", str(certificate), "-noout", "-subject", "-nameopt", "multiline"
    ).decode()
    if re.findall(r"^\s*commonName\s*=\s*(.*?)\s*$", subject, re.MULTILINE) != [name]:
        raise ReleaseError(EXIT_IDENTITY, "identity-name", "Certificate common name does not match")
    with tempfile.TemporaryDirectory() as work:
        challenge, signature = Path(work) / "challenge", Path(work) / "signature"
        challenge.write_bytes(os.urandom(32))
        public = Path(work) / "public.pem"
        public.write_bytes(run("openssl", "x509", "-in", str(certificate), "-noout", "-pubkey"))
        # Signing proves the key loads in, and is usable by, this TPM.
        try:
            run(
                "openssl",
                "dgst",
                *PROVIDERS,
                "-sha256",
                "-sign",
                str(key),
                "-out",
                str(signature),
                str(challenge),
            )
        except ReleaseError as error:
            raise ReleaseError(
                EXIT_IDENTITY, "identity-foreign-tpm", "Identity key does not load in this TPM"
            ) from error
        try:
            run(
                "openssl",
                "dgst",
                "-sha256",
                "-verify",
                str(public),
                "-signature",
                str(signature),
                str(challenge),
            )
        except ReleaseError as error:
            raise ReleaseError(
                EXIT_IDENTITY,
                "identity-mismatch",
                "Certificate does not belong to the TPM identity key",
            ) from error


def _curl_config(url: str, *, token: str | None = None, body: dict | None = None) -> bytes:
    # Passed on stdin so tokens never appear in process arguments.
    def quote(value: str) -> str:
        # A newline would start a new curl directive; server-supplied tokens are untrusted.
        if any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
            raise ReleaseError(
                EXIT_CONFIG, "release-malformed", "Control characters in release request"
            )
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    lines = [f"url = {quote(url)}", 'header = "Content-Type: application/json"']
    if token is not None:
        lines.append(f"header = {quote('X-Vault-Token: ' + token)}")
    if body is not None:
        lines.append(f"data = {quote(json.dumps(body))}")
    return ("\n".join(lines) + "\n").encode()


def curl_arguments(ca: Path, certificate: Path, key: Path) -> list[str]:
    return [
        "curl",
        # Must be first: ignore ~/.curlrc and CURL_HOME so no ambient option applies.
        "--disable",
        "--silent",
        "--show-error",
        "--noproxy",
        "*",
        "--proto",
        "=https",
        "--connect-timeout",
        "5",
        "--max-time",
        "15",
        *CURL_TLS,
        "--cacert",
        str(ca),
        "--cert",
        str(certificate),
        "--key",
        str(key),
        "--write-out",
        "\n%{http_code}",
        "--config",
        "-",
    ]


def _request(arguments: list[str], config: bytes) -> tuple[int, dict]:
    result = subprocess.run(arguments, input=config, capture_output=True, check=False)
    if result.returncode in (6, 7, 28):
        raise ReleaseError(
            EXIT_UNREACHABLE,
            "release-unreachable",
            f"Release service unreachable (curl exit {result.returncode})",
        )
    if result.returncode:
        # TLS failures include pinning and client-certificate rejection.
        raise ReleaseError(
            EXIT_DENIED,
            "release-tls-rejected",
            f"TLS connection to release service failed (curl exit {result.returncode})",
        )
    payload, _, status = result.stdout.rpartition(b"\n")
    try:
        document = json.loads(payload) if payload.strip() else {}
        if not isinstance(document, dict):
            raise ValueError("response is not an object")
        return int(status), document
    except ValueError as error:
        raise ReleaseError(
            EXIT_CONFIG, "release-malformed", "Malformed release response"
        ) from error


def _classify(status: int, stage: str) -> None:
    if status == 200:
        return
    if status == 503:
        raise ReleaseError(
            EXIT_SEALED, "release-sealed", f"Release service sealed or unavailable ({stage})"
        )
    if status == 404:
        raise ReleaseError(EXIT_NOT_FOUND, "release-not-found", f"No release record ({stage})")
    if status in (400, 401, 403):
        raise ReleaseError(
            EXIT_DENIED, "release-denied", f"Release denied ({stage}, HTTP {status})"
        )
    raise ReleaseError(EXIT_CONFIG, "release-unexpected", f"Unexpected HTTP {status} ({stage})")


def fetch(
    url: str, ca: Path, certificate: Path, key: Path, name: str, volume: str, mount: str
) -> bytes:
    base = require_release_url(url) + "/v1/"
    for value, field in ((name, "name"), (volume, "volume"), (mount, "mount")):
        require_segment(value, field)
    # A plaintext or exportable key would satisfy mTLS but defeat hardware binding (ENC-06).
    try:
        require_identity_attributes(decode_tss2(key.read_text()))
    except (OSError, UnicodeDecodeError, ValueError, IndexError) as error:
        raise ReleaseError(
            EXIT_IDENTITY, "identity-malformed", "Unreadable identity key"
        ) from error
    arguments = curl_arguments(ca, certificate, key)
    status, login = _request(arguments, _curl_config(base + "auth/cert/login", body={"name": name}))
    _classify(status, "login")
    token = _field(login, "auth", "client_token")
    if not isinstance(token, str) or not token:
        raise ReleaseError(EXIT_DENIED, "release-denied", "Login returned no token")
    # The single-use token is consumed by this read; nothing is cached.
    status, record = _request(
        arguments, _curl_config(f"{base}{mount}/data/{name}/{volume}", token=token)
    )
    _classify(status, "read")
    secret = _field(record, "data", "data", "key")
    if not isinstance(secret, str) or not secret:
        raise ReleaseError(EXIT_NOT_FOUND, "release-not-found", "Release record has no key")
    return secret.encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("identity-create", help="Create the TPM identity key and CSR once")
    create.add_argument("--key", type=Path, required=True)
    create.add_argument("--csr", type=Path, required=True)
    create.add_argument("--name", required=True)
    create.add_argument(
        "--create-srk",
        action="store_true",
        help=f"Persist the TCG SRK at {SRK_HANDLE:#x} if it is absent",
    )
    check = sub.add_parser(
        "identity-check", help="Prove the key is TPM-bound and matches the certificate"
    )
    check.add_argument("--key", type=Path, required=True)
    check.add_argument("--cert", type=Path, required=True)
    check.add_argument("--name", required=True)
    release = sub.add_parser("fetch", help="Write one volume's released secret to stdout")
    release.add_argument("--url", required=True)
    release.add_argument("--ca", type=Path, required=True)
    release.add_argument("--cert", type=Path, required=True)
    release.add_argument("--key", type=Path, required=True)
    release.add_argument("--name", required=True)
    release.add_argument("--volume", required=True)
    release.add_argument("--mount", default="volume-release")
    args = parser.parse_args()
    try:
        if args.command == "identity-create":
            identity_create(args.key, args.csr, args.name, args.create_srk)
            print(f"Created TPM identity; submit {args.csr} for enrollment")
        elif args.command == "identity-check":
            identity_check(args.key, args.cert, args.name)
            print("TPM identity verified")
        else:
            secret = fetch(
                args.url, args.ca, args.cert, args.key, args.name, args.volume, args.mount
            )
            sys.stdout.buffer.write(secret)
            sys.stdout.buffer.flush()
    except ReleaseError as error:
        print(f"ERROR {error.reason}: {error}", file=sys.stderr)
        sys.exit(error.code)


if __name__ == "__main__":
    main()
