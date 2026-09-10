#!/usr/bin/env python3
"""Exercise the Lux data plane using an installed LX-Annotate wheel.

This is an explicit cross-package acceptance harness, not a pytest module. It
never imports LX-Annotate into the Lux test environment. The supplied Python
must contain the candidate wheel, and the child process proves the import came
from that wheel's site-packages directory before running the transfer.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import ipaddress
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, x25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from lx_administration.storage.data_plane import (
    BlobStore,
    StorageHTTPServer,
    _build_tls_context,
)
from lx_administration.storage.manager import StorageNodeContract


_HUB_IDENTITY = "spiffe://endoreg/hub/gs-02"
_CLIENT = r"""
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import site
import sys

import lx_annotate
import celery
import cryptography
import endoreg_db
import lx_dtypes
import pydantic
import requests

expected_root = Path(os.environ["EXPECTED_LX_WHEEL_ROOT"]).resolve()
if not sys.flags.isolated or not sys.flags.no_user_site or site.ENABLE_USER_SITE:
    raise RuntimeError("wheel client must run isolated with user site disabled")
package_origins = {
    name: Path(module.__file__).resolve()
    for name, module in {
        "lx_annotate": lx_annotate,
        "endoreg_db": endoreg_db,
        "lx_dtypes": lx_dtypes,
        "celery": celery,
        "cryptography": cryptography,
        "pydantic": pydantic,
        "requests": requests,
    }.items()
}
outside = {
    name: str(origin)
    for name, origin in package_origins.items()
    if not origin.is_relative_to(expected_root)
}
if outside:
    raise RuntimeError(
        f"packages resolved outside isolated wheel environment: {outside}"
    )
if version("lx-annotate") != os.environ["EXPECTED_LX_VERSION"]:
    raise RuntimeError("unexpected lx-annotate wheel version")
if version("endoreg-db") != os.environ["EXPECTED_ENDOREG_VERSION"]:
    raise RuntimeError("unexpected endoreg-db wheel version")

from lx_annotate.hub.storage_transfer_client import (
    StorageTransferArtifactKind,
    StorageTransferClient,
    StorageTransferClientContract,
    StorageTransferPeer,
    prepare_storage_envelope,
)

declared_peer = StorageTransferPeer(
    node_key="gs-01",
    display_name="gs-01",
    failure_domain="gs-01",
    residency_key="de",
    placement_weight=100,
    artifact_kinds={StorageTransferArtifactKind.PROCESSED_REPORT},
    endpoint=os.environ["STORAGE_ENDPOINT"],
    ca_certificate_file=Path(os.environ["STORAGE_CA"]),
    client_certificate_file=Path(os.environ["STORAGE_CLIENT_CERT"]),
    client_key_file=Path(os.environ["STORAGE_CLIENT_KEY"]),
    recipient_public_key_file=Path(os.environ["STORAGE_RECIPIENT_PUBLIC"]),
)
peer = StorageTransferClientContract(nodes=[declared_peer]).peer("gs-01")
client = StorageTransferClient(peer, timeout_seconds=10)
source = Path(os.environ["STORAGE_SOURCE"])
prepared = prepare_storage_envelope(
    peer=peer,
    source_path=source,
    staging_directory=Path(os.environ["STORAGE_STAGING"]),
    idempotency_key="wheel-contract-store-0001",
    artifact_kind=StorageTransferArtifactKind.PROCESSED_REPORT,
)
receipt = client.store(prepared, idempotency_key="wheel-contract-store-0001")
expected_digest = hashlib.sha256(source.read_bytes()).hexdigest()
assert receipt.plaintext_sha256 == expected_digest
assert client.health().node_id == "gs-01"
assert client.capacity().accepting_writes is True
assert client.verify(prepared.ciphertext_sha256).valid is True
destination = Path(os.environ["STORAGE_DESTINATION"])
client.fetch_plaintext(
    ciphertext_sha256=prepared.ciphertext_sha256,
    expected_plaintext_sha256=expected_digest,
    expected_plaintext_size=source.stat().st_size,
    destination=destination,
)
assert client.delete(
    prepared.ciphertext_sha256,
    idempotency_key="wheel-contract-delete-0001",
).deleted is True
print(
    json.dumps(
        {
            "packages": {
                key: str(value) for key, value in package_origins.items()
            },
            "status": "passed",
        }
    )
)
"""


def _write(path: Path, value: bytes, *, private: bool = False) -> Path:
    path.write_bytes(value)
    path.chmod(0o600 if private else 0o644)
    return path


def _private_local_ipv4() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("172.16.255.1", 9))
        value = str(probe.getsockname()[0])
    address = ipaddress.ip_address(value)
    if not address.is_private or address.is_loopback:
        raise RuntimeError("wheel contract test needs a private local IPv4")
    return value


def _free_port(address: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((address, 0))
        return int(listener.getsockname()[1])


def _identities(root: Path, server_address: str) -> tuple[Path, Path, Path, Path, Path]:
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "storage-test-ca")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    def issue(
        name: str,
        san: x509.SubjectAlternativeName,
        usage: x509.ObjectIdentifier,
    ) -> tuple[Path, Path]:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
            .issuer_name(ca_name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(san, critical=False)
            .add_extension(x509.ExtendedKeyUsage([usage]), critical=True)
            .sign(ca_key, hashes.SHA256())
        )
        return (
            _write(root / f"{name}.crt", cert.public_bytes(serialization.Encoding.PEM)),
            _write(
                root / f"{name}.key",
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                ),
                private=True,
            ),
        )

    ca = _write(root / "ca.crt", ca_cert.public_bytes(serialization.Encoding.PEM))
    server_cert, server_key = issue(
        "storage-server",
        x509.SubjectAlternativeName(
            [x509.IPAddress(ipaddress.ip_address(server_address))]
        ),
        ExtendedKeyUsageOID.SERVER_AUTH,
    )
    client_cert, client_key = issue(
        "hub-client",
        x509.SubjectAlternativeName([x509.UniformResourceIdentifier(_HUB_IDENTITY)]),
        ExtendedKeyUsageOID.CLIENT_AUTH,
    )
    return ca, server_cert, server_key, client_cert, client_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--wheel-site-packages", type=Path, required=True)
    parser.add_argument("--lx-version", default="0.9.62")
    parser.add_argument("--endoreg-version", default="1.0.10.0")
    args = parser.parse_args()
    wheel_root = args.wheel_site_packages.resolve(strict=True)
    python = args.python.expanduser().absolute()
    if not python.is_file():
        raise ValueError("--python must identify the candidate virtualenv interpreter")

    with tempfile.TemporaryDirectory(prefix="lx-storage-wheel-contract-") as raw:
        root = Path(raw)
        address = _private_local_ipv4()
        port = _free_port(address)
        ca, server_cert, server_key, client_cert, client_key = _identities(
            root, address
        )
        recipient = x25519.X25519PrivateKey.generate()
        recipient_private = _write(
            root / "recipient-private.pem",
            recipient.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
            private=True,
        )
        recipient_public = _write(
            root / "recipient-public.pem",
            recipient.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ),
        )
        storage_root = root / "storage"
        storage_root.mkdir()
        encrypted_device = root / "encrypted-device"
        encrypted_device.touch()
        contract = StorageNodeContract(
            node_id="gs-01",
            storage_root=storage_root,
            encrypted_device=encrypted_device,
            listen_address=address,
            port=port,
            allowed_hub_addresses=[address],
            allowed_hub_identities=[_HUB_IDENTITY],
            hub_identity_operations={
                _HUB_IDENTITY: {
                    "health",
                    "capacity",
                    "store",
                    "fetch_ciphertext",
                    "fetch_plaintext",
                    "verify",
                    "delete",
                }
            },
            tls_ca_file=ca,
            tls_cert_file=server_cert,
            tls_key_file=server_key,
            recipient_private_identity_files=[recipient_private],
            capacity_warning_percent=97,
            capacity_stop_percent=99,
            capacity_recovery_percent=95,
            capacity_reserve_bytes=1,
            max_object_bytes=1024 * 1024,
        )
        server = StorageHTTPServer(
            contract,
            BlobStore(
                contract,
                mount_guard=lambda _: True,
                mount_source_resolver=lambda _: encrypted_device,
            ),
        )
        server.socket = _build_tls_context(contract).wrap_socket(
            server.socket, server_side=True
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        source = root / "source.bin"
        payload = b"processed report wheel contract\n" * 64
        source.write_bytes(payload)
        destination = root / "destination.bin"
        try:
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            environment.pop("PYTHONHOME", None)
            environment.update(
                {
                    "EXPECTED_LX_WHEEL_ROOT": str(wheel_root),
                    "EXPECTED_LX_VERSION": str(args.lx_version),
                    "EXPECTED_ENDOREG_VERSION": str(args.endoreg_version),
                    "STORAGE_ENDPOINT": f"https://{address}:{port}",
                    "STORAGE_CA": str(ca),
                    "STORAGE_CLIENT_CERT": str(client_cert),
                    "STORAGE_CLIENT_KEY": str(client_key),
                    "STORAGE_RECIPIENT_PUBLIC": str(recipient_public),
                    "STORAGE_SOURCE": str(source),
                    "STORAGE_STAGING": str(root / "staging"),
                    "STORAGE_DESTINATION": str(destination),
                }
            )
            subprocess.run(
                [str(python), "-I", "-s", "-c", _CLIENT],
                check=True,
                cwd=root,
                env=environment,
            )
            if destination.read_bytes() != payload:
                raise RuntimeError("wheel client plaintext round trip changed bytes")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)


if __name__ == "__main__":
    main()
