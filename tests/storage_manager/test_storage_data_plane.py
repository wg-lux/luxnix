from __future__ import annotations

import base64
import fcntl
import hashlib
import io
import os
import threading
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from lx_administration.storage.data_plane import (
    BlobStore,
    DataPlaneError,
    EnvelopeMetadata,
    InventoryItem,
    InventoryPage,
    StorageRequestHandler,
    StorageHTTPServer,
    WIRE_CONTRACT_HEADER,
    WIRE_CONTRACT_VERSION,
    _decode_inventory_cursor,
    _build_tls_context,
    _peer_identities,
    _validate_identity_files,
)
from lx_administration.storage.envelope import (
    load_recipient_private_key,
    recipient_key_id,
)
from lx_administration.storage.manager import StorageNodeContract


def _contract(root: Path, **overrides: object) -> StorageNodeContract:
    encrypted_device = root / "encrypted-device"
    encrypted_device.touch(exist_ok=True)
    recipient_path = root / "recipient-private.pem"
    if not recipient_path.exists():
        recipient_path.write_bytes(
            X25519PrivateKey.generate().private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    values: dict[str, object] = {
        "node_id": "storage-01",
        "storage_root": root,
        "encrypted_device": encrypted_device,
        "listen_address": "10.0.0.2",
        "port": 9443,
        "allowed_hub_addresses": ["10.0.0.1"],
        "allowed_hub_identities": ["spiffe://endoreg/hub/primary"],
        "hub_identity_operations": {
            "spiffe://endoreg/hub/primary": {
                "health",
                "capacity",
                "inventory",
                "store",
                "fetch_ciphertext",
                "fetch_plaintext",
                "verify",
                "delete",
            }
        },
        "tls_ca_file": "/run/ca",
        "tls_cert_file": "/run/cert",
        "tls_key_file": "/run/key",
        "recipient_private_identity_file": recipient_path,
        "capacity_reserve_bytes": 1,
        "capacity_recovery_percent": 96,
        "capacity_warning_percent": 97,
        "capacity_stop_percent": 99,
        "max_object_bytes": 1024 * 1024,
    }
    values.update(overrides)
    return StorageNodeContract.model_validate(values)


def _store(root: Path, **overrides: object) -> BlobStore:
    contract = _contract(root, **overrides)
    return BlobStore(
        contract,
        mount_guard=lambda _: True,
        mount_source_resolver=lambda _: contract.encrypted_device,
    )


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _envelope(
    store: BlobStore, plaintext: bytes, *, identity_path: Path | None = None
) -> EnvelopeMetadata:
    selected_path = identity_path or store.contract.recipient_private_identity_file
    assert selected_path is not None
    private = load_recipient_private_key(selected_path)
    return EnvelopeMetadata(
        node_id=store.contract.node_id,
        artifact_kind="anonymized_video",
        recipient_key_id=recipient_key_id(private),
        plaintext_sha256=hashlib.sha256(plaintext).hexdigest(),
        plaintext_size=len(plaintext),
        ephemeral_public_key=_b64(b"e" * 32),
        wrap_salt=_b64(b"s" * 16),
        wrap_nonce=_b64(b"w" * 12),
        wrapped_data_encryption_key=_b64(b"k" * 48),
        payload_nonce=_b64(b"p" * 12),
        payload_tag=_b64(b"t" * 16),
    )


def test_recipient_keyring_accepts_current_and_retiring_identity(
    tmp_path: Path,
) -> None:
    paths: list[Path] = []
    for name in ("retiring.pem", "current.pem"):
        path = tmp_path / name
        path.write_bytes(
            X25519PrivateKey.generate().private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        paths.append(path)
    store = _store(
        tmp_path,
        recipient_private_identity_file=None,
        recipient_private_identity_files=paths,
    )
    for index, path in enumerate(paths):
        payload = f"ciphertext-{index}".encode()
        digest = hashlib.sha256(payload).hexdigest()
        assert store.store(
            digest,
            io.BytesIO(payload),
            content_length=len(payload),
            operation_key=f"keyring-store-operation-{index:04d}",
            envelope=_envelope(store, payload, identity_path=path),
        )


def test_store_fetch_verify_and_replay_are_content_addressed(tmp_path: Path) -> None:
    payload = b"opaque-encrypted-payload"
    digest = hashlib.sha256(payload).hexdigest()
    store = _store(tmp_path)

    assert store.store(
        digest,
        io.BytesIO(payload),
        content_length=len(payload),
        operation_key="store-operation-0001",
        envelope=_envelope(store, payload),
    )
    assert store.verify(digest, expected_size=len(payload))
    stream, size = store.open_blob(digest)
    with stream:
        assert stream.read() == payload
    assert size == len(payload)
    assert not store.store(
        digest,
        io.BytesIO(payload),
        content_length=len(payload),
        operation_key="store-operation-0001",
        envelope=_envelope(store, payload),
    )


def test_inventory_is_typed_sorted_and_uses_an_opaque_exclusive_cursor(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    payloads = (b"inventory-c", b"inventory-a", b"inventory-b")
    for index, payload in enumerate(payloads):
        store.store(
            hashlib.sha256(payload).hexdigest(),
            io.BytesIO(payload),
            content_length=len(payload),
            operation_key=f"inventory-store-{index:04d}",
            envelope=_envelope(store, payload),
        )

    first = store.inventory(cursor=None, limit=2)

    expected_digests = sorted(hashlib.sha256(value).hexdigest() for value in payloads)
    assert [item.ciphertext_sha256 for item in first.items] == expected_digests[:2]
    assert first.next_cursor is not None
    assert first.next_cursor != expected_digests[1]
    assert _decode_inventory_cursor(first.next_cursor) == expected_digests[1]
    assert all(item.ciphertext_size > 0 for item in first.items)
    assert all(item.plaintext_size > 0 for item in first.items)
    assert all(item.artifact_kind == "anonymized_video" for item in first.items)

    second = store.inventory(cursor=first.next_cursor, limit=2)

    assert [item.ciphertext_sha256 for item in second.items] == expected_digests[2:]
    assert second.next_cursor is None


@pytest.mark.parametrize("limit", [0, 1001])
def test_inventory_rejects_unbounded_limits(tmp_path: Path, limit: int) -> None:
    with pytest.raises(DataPlaneError) as rejected:
        _store(tmp_path).inventory(cursor=None, limit=limit)
    assert rejected.value.status == HTTPStatus.BAD_REQUEST


def test_inventory_rejects_malformed_opaque_cursor(tmp_path: Path) -> None:
    with pytest.raises(DataPlaneError) as rejected:
        _store(tmp_path).inventory(cursor="not-a-valid-cursor", limit=100)
    assert rejected.value.status == HTTPStatus.BAD_REQUEST


def test_inventory_http_response_has_the_additive_v1_wire_shape() -> None:
    digest = hashlib.sha256(b"inventory-wire-item").hexdigest()
    cursor = "opaque-next-cursor"
    requested: list[tuple[str | None, int]] = []
    item = InventoryItem(
        ciphertext_sha256=digest,
        ciphertext_size=123,
        plaintext_sha256=hashlib.sha256(b"plaintext").hexdigest(),
        plaintext_size=9,
        recipient_key_id="1" * 64,
        artifact_kind="anonymized_video",
    )
    store = SimpleNamespace(
        inventory=lambda *, cursor, limit: (
            requested.append((cursor, limit))
            or InventoryPage(items=(item,), next_cursor=None)
        )
    )
    handler = object.__new__(StorageRequestHandler)
    handler.path = f"/v1/inventory?cursor={cursor}&limit=7"
    handler.server = SimpleNamespace(
        contract=SimpleNamespace(node_id="storage-01"), store=store
    )
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []
    handler._send_json = lambda status, payload: responses.append((status, payload))

    handler._get()

    assert requested == [(cursor, 7)]
    assert responses == [
        (
            HTTPStatus.OK,
            {
                "contract_version": WIRE_CONTRACT_VERSION,
                "node_id": "storage-01",
                "items": [vars(item)],
                "next_cursor": None,
            },
        )
    ]


def test_inventory_route_uses_its_own_mtls_allowlisted_operation() -> None:
    handler = object.__new__(StorageRequestHandler)
    handler.path = "/v1/inventory?limit=1"
    dispatched: list[str] = []
    handler._dispatch = lambda operation, _action: dispatched.append(operation)

    handler.do_GET()

    assert dispatched == ["inventory"]


@pytest.mark.parametrize(
    "query",
    ["unknown=value", "limit=1&limit=2", "cursor=", "limit=not-an-int"],
)
def test_inventory_http_query_is_strict(query: str) -> None:
    handler = object.__new__(StorageRequestHandler)
    handler.path = f"/v1/inventory?{query}"
    handler.server = SimpleNamespace(
        contract=SimpleNamespace(node_id="storage-01"),
        store=SimpleNamespace(inventory=lambda **_kwargs: None),
    )

    with pytest.raises(DataPlaneError) as rejected:
        handler._get()

    assert rejected.value.status == HTTPStatus.BAD_REQUEST


def test_store_rejects_hash_mismatch_and_missing_envelope_metadata(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    digest = hashlib.sha256(b"expected").hexdigest()

    with pytest.raises(DataPlaneError) as mismatch:
        store.store(
            digest,
            io.BytesIO(b"different"),
            content_length=len(b"different"),
            operation_key="store-operation-0002",
            envelope=_envelope(store, b"different"),
        )
    assert mismatch.value.status == HTTPStatus.UNPROCESSABLE_ENTITY

    with pytest.raises(ValueError, match="absent"):
        EnvelopeMetadata.from_header("")


def test_idempotency_key_cannot_be_reused_for_another_object(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = b"first"
    second = b"second"
    key = "store-operation-reused"
    store.store(
        hashlib.sha256(first).hexdigest(),
        io.BytesIO(first),
        content_length=len(first),
        operation_key=key,
        envelope=_envelope(store, first),
    )

    with pytest.raises(DataPlaneError) as conflict:
        store.store(
            hashlib.sha256(second).hexdigest(),
            io.BytesIO(second),
            content_length=len(second),
            operation_key=key,
            envelope=_envelope(store, second),
        )
    assert conflict.value.status == HTTPStatus.CONFLICT


def test_existing_ciphertext_rejects_conflicting_envelope_declaration(
    tmp_path: Path,
) -> None:
    payload = b"ciphertext"
    digest = hashlib.sha256(payload).hexdigest()
    store = _store(tmp_path)
    store.store(
        digest,
        io.BytesIO(payload),
        content_length=len(payload),
        operation_key="store-envelope-original",
        envelope=_envelope(store, payload),
    )

    with pytest.raises(DataPlaneError) as conflict:
        store.store(
            digest,
            io.BytesIO(payload),
            content_length=len(payload),
            operation_key="store-envelope-conflict",
            envelope=_envelope(store, payload).model_copy(
                update={"payload_tag": _b64(b"u" * 16)}
            ),
        )
    assert conflict.value.status == HTTPStatus.CONFLICT


def test_store_retry_repairs_crash_after_object_rename(tmp_path: Path) -> None:
    payload = b"ciphertext-after-lost-ack"
    digest = hashlib.sha256(payload).hexdigest()
    store = _store(tmp_path)
    destination = store._object_path(digest)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(payload)

    assert not store.store(
        digest,
        io.BytesIO(payload),
        content_length=len(payload),
        operation_key="store-lost-ack-recovery",
        envelope=_envelope(store, payload),
    )
    assert store._read_receipt(store.metadata / digest[:2] / digest[2:]) is not None


def test_fetch_and_delete_fail_closed_on_corrupted_ciphertext(tmp_path: Path) -> None:
    payload = b"ciphertext-before-corruption"
    digest = hashlib.sha256(payload).hexdigest()
    store = _store(tmp_path)
    store.store(
        digest,
        io.BytesIO(payload),
        content_length=len(payload),
        operation_key="store-before-corruption",
        envelope=_envelope(store, payload),
    )
    store._object_path(digest).write_bytes(b"corrupted")

    with pytest.raises(DataPlaneError) as fetch_error:
        store.open_verified_blob(digest)
    assert fetch_error.value.status == HTTPStatus.CONFLICT
    with pytest.raises(DataPlaneError) as delete_error:
        store.delete(
            digest,
            operation_key="delete-corrupt-object",
            precondition=digest,
        )
    assert delete_error.value.status == HTTPStatus.CONFLICT


def test_delete_requires_exact_digest_and_is_replay_safe(tmp_path: Path) -> None:
    payload = b"ciphertext"
    digest = hashlib.sha256(payload).hexdigest()
    store = _store(tmp_path)
    store.store(
        digest,
        io.BytesIO(payload),
        content_length=len(payload),
        operation_key="store-operation-delete",
        envelope=_envelope(store, payload),
    )
    with pytest.raises(DataPlaneError) as precondition:
        store.delete(
            digest,
            operation_key="delete-operation-0001",
            precondition="0" * 64,
        )
    assert precondition.value.status == HTTPStatus.PRECONDITION_FAILED

    assert store.delete(
        digest, operation_key="delete-operation-0001", precondition=digest
    )
    assert not store.delete(
        digest, operation_key="delete-operation-0001", precondition=digest
    )
    assert not store.verify(digest)


def test_delete_retry_finishes_crash_after_quarantine_rename(tmp_path: Path) -> None:
    payload = b"quarantined-ciphertext"
    digest = hashlib.sha256(payload).hexdigest()
    key = "delete-lost-ack-recovery"
    store = _store(tmp_path)
    store.store(
        digest,
        io.BytesIO(payload),
        content_length=len(payload),
        operation_key="store-before-delete-crash",
        envelope=_envelope(store, payload),
    )
    source = store._object_path(digest)
    quarantine = (
        store.quarantine / f"{digest}.{hashlib.sha256(key.encode()).hexdigest()}"
    )
    source.replace(quarantine)

    assert not store.delete(digest, operation_key=key, precondition=digest)
    assert not quarantine.exists()
    assert store._read_receipt(store._receipt_path("delete", key)) == {"digest": digest}


def test_janitor_removes_only_stale_and_receipt_backed_crash_artifacts(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    old = 1_000.0
    incoming = store.incoming / "stale-partial"
    incoming.write_bytes(b"partial")
    os.utime(incoming, (old, old))

    payload = b"receipt-backed-quarantine"
    digest = hashlib.sha256(payload).hexdigest()
    key = "delete-janitor-recovery"
    receipt_key = hashlib.sha256(key.encode()).hexdigest()
    quarantine = store.quarantine / f"{digest}.{receipt_key}"
    quarantine.write_bytes(payload)
    os.utime(quarantine, (old, old))
    store._write_receipt(store._receipt_path("delete", key), {"digest": digest})

    orphan_digest = hashlib.sha256(b"orphan").hexdigest()
    orphan = store.metadata / orphan_digest[:2] / orphan_digest[2:]
    store._write_receipt(orphan, {"digest": orphan_digest})
    os.utime(orphan, (old, old))

    unproved = store.quarantine / f"{'f' * 64}.{'e' * 64}"
    unproved.write_bytes(b"must-remain")
    os.utime(unproved, (old, old))

    result = store.run_janitor(minimum_age_seconds=100, now=2_000.0)

    assert result.removed_incoming == 1
    assert result.completed_quarantine == 1
    assert result.removed_orphan_metadata == 1
    assert unproved.exists()


def test_janitor_preserves_corrupt_receipt_and_continues(tmp_path: Path) -> None:
    store = _store(tmp_path)
    corrupt = store.receipts / "delete" / ("a" * 64)
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("{broken", encoding="utf-8")
    stale = store.incoming / "stale"
    stale.write_bytes(b"partial")
    os.utime(stale, (1_000.0, 1_000.0))

    result = store.run_janitor(
        minimum_age_seconds=100,
        max_entries=100,
        now=2_000.0,
    )

    assert result.removed_incoming == 1
    assert result.quarantined_corrupt_receipts == 1
    assert corrupt.read_text(encoding="utf-8") == "{broken"
    assert len(list(store.corrupt_receipts.iterdir())) == 1


def test_janitor_scan_is_bounded(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for index in range(3):
        path = store.incoming / f"stale-{index}"
        path.write_bytes(b"partial")
        os.utime(path, (1_000.0, 1_000.0))

    result = store.run_janitor(
        minimum_age_seconds=100,
        max_entries=1,
        now=2_000.0,
    )

    assert result.scanned_entries == 1
    assert result.scan_limit_reached
    assert result.removed_incoming == 1
    assert len(list(store.incoming.iterdir())) == 2


def test_mutations_create_shared_interprocess_lock(tmp_path: Path) -> None:
    payload = b"locked-ciphertext"
    digest = hashlib.sha256(payload).hexdigest()
    store = _store(tmp_path)

    store.store(
        digest,
        io.BytesIO(payload),
        content_length=len(payload),
        operation_key="store-with-process-lock",
        envelope=_envelope(store, payload),
    )

    assert store.operation_lock_path.is_file()
    assert store.operation_lock_path.stat().st_mode & 0o077 == 0

    with store._exclusive_operations():
        competing_fd = os.open(store.operation_lock_path, os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(competing_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(competing_fd)


def test_mount_loss_fails_closed_for_every_operation(tmp_path: Path) -> None:
    mounted = True

    def guard(_: Path) -> bool:
        return mounted

    contract = _contract(tmp_path)
    store = BlobStore(
        contract,
        mount_guard=guard,
        mount_source_resolver=lambda _: contract.encrypted_device,
    )
    mounted = False
    with pytest.raises(DataPlaneError) as unavailable:
        store.capacity()
    assert unavailable.value.status == HTTPStatus.SERVICE_UNAVAILABLE


def test_wrong_device_remount_fails_closed_on_next_operation(tmp_path: Path) -> None:
    contract = _contract(tmp_path)
    wrong_device = tmp_path / "wrong-device"
    wrong_device.touch()
    current_device = contract.encrypted_device
    store = BlobStore(
        contract,
        mount_guard=lambda _: True,
        mount_source_resolver=lambda _: current_device,
    )
    current_device = wrong_device

    with pytest.raises(DataPlaneError, match="wrong device") as unavailable:
        store.capacity()
    assert unavailable.value.status == HTTPStatus.SERVICE_UNAVAILABLE


def test_peer_identity_uses_san_and_never_common_name() -> None:
    certificate = {
        "subjectAltName": (("URI", "spiffe://endoreg/hub/primary"),),
        "subject": ((("commonName", "untrusted-cn"),),),
    }
    assert _peer_identities(certificate) == {"spiffe://endoreg/hub/primary"}


def test_peer_identity_is_restricted_to_configured_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lx_administration.storage.data_plane as data_plane

    class FakeSocket:
        def getpeercert(self):
            return {"subjectAltName": (("URI", "spiffe://endoreg/hub/primary"),)}

    contract = _contract(
        tmp_path,
        hub_identity_operations={
            "spiffe://endoreg/hub/primary": {"health", "capacity", "inventory"}
        },
    )
    handler = object.__new__(StorageRequestHandler)
    handler.client_address = ("10.0.0.1", 12345)
    handler.connection = FakeSocket()
    handler.server = SimpleNamespace(contract=contract)
    monkeypatch.setattr(data_plane.ssl, "SSLSocket", FakeSocket)

    handler._authenticate("health")
    handler._authenticate("inventory")
    with pytest.raises(DataPlaneError) as denied:
        handler._authenticate("delete")
    assert denied.value.status == HTTPStatus.FORBIDDEN


def test_peer_certificate_cannot_union_multiple_allowed_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lx_administration.storage.data_plane as data_plane

    class FakeSocket:
        def getpeercert(self):
            return {
                "subjectAltName": (
                    ("URI", "spiffe://endoreg/hub/primary"),
                    ("URI", "spiffe://endoreg/hub/retiring"),
                )
            }

    contract = _contract(
        tmp_path,
        allowed_hub_identities=[
            "spiffe://endoreg/hub/primary",
            "spiffe://endoreg/hub/retiring",
        ],
        hub_identity_operations={
            "spiffe://endoreg/hub/primary": {"health"},
            "spiffe://endoreg/hub/retiring": {"delete"},
        },
    )
    handler = object.__new__(StorageRequestHandler)
    handler.client_address = ("10.0.0.1", 12345)
    handler.connection = FakeSocket()
    handler.server = SimpleNamespace(contract=contract)
    monkeypatch.setattr(data_plane.ssl, "SSLSocket", FakeSocket)

    with pytest.raises(DataPlaneError, match="ambiguous") as denied:
        handler._authenticate("delete")
    assert denied.value.status == HTTPStatus.FORBIDDEN


def test_recipient_rotation_rejects_duplicate_key_material(tmp_path: Path) -> None:
    first = tmp_path / "first.pem"
    second = tmp_path / "second.pem"
    key = X25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    first.write_bytes(key)
    second.write_bytes(key)
    first.chmod(0o640)
    second.chmod(0o640)
    contract = _contract(
        tmp_path,
        tls_ca_file=first,
        tls_cert_file=first,
        tls_key_file=first,
        recipient_private_identity_file=None,
        recipient_private_identity_files=[first, second],
    )

    with pytest.raises(RuntimeError, match="distinct keys"):
        _validate_identity_files(contract)


def test_tls_context_requires_client_cert_and_tls13(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lx_administration.storage.data_plane as data_plane

    class FakeContext:
        minimum_version: object = None
        verify_mode: object = None
        ca: str | None = None
        cert: tuple[str, str] | None = None

        def load_verify_locations(self, *, cafile: str) -> None:
            self.ca = cafile

        def load_cert_chain(self, *, certfile: str, keyfile: str) -> None:
            self.cert = (certfile, keyfile)

    context = FakeContext()
    monkeypatch.setattr(data_plane.ssl, "SSLContext", lambda _: context)
    built = _build_tls_context(_contract(tmp_path))

    assert built is context
    assert context.minimum_version == data_plane.ssl.TLSVersion.TLSv1_3
    assert context.verify_mode == data_plane.ssl.CERT_REQUIRED
    assert context.ca == "/run/ca"
    assert context.cert == ("/run/cert", "/run/key")


def test_dispatch_error_closes_connection_before_returning_error() -> None:
    handler = object.__new__(StorageRequestHandler)
    handler.close_connection = False
    handler._authenticate = lambda _operation: (_ for _ in ()).throw(
        DataPlaneError(HTTPStatus.FORBIDDEN, "denied")
    )
    responses: list[HTTPStatus] = []
    handler._send_json = lambda status, payload: responses.append(status)

    handler._dispatch("health", lambda: None)

    assert handler.close_connection
    assert responses == [HTTPStatus.FORBIDDEN]


def test_json_responses_identify_the_exact_wire_contract() -> None:
    handler = object.__new__(StorageRequestHandler)
    headers: dict[str, str] = {}
    handler.wfile = io.BytesIO()
    handler.send_response = lambda _status: None
    handler.send_header = lambda name, value: headers.__setitem__(name, value)
    handler.end_headers = lambda: None

    handler._send_json(HTTPStatus.OK, {"status": "ready"})

    assert headers[WIRE_CONTRACT_HEADER] == WIRE_CONTRACT_VERSION
    assert headers["Content-Type"] == "application/json"


def test_server_rejects_connections_above_concurrency_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = object.__new__(StorageHTTPServer)
    server._request_slots = threading.BoundedSemaphore(1)
    accepted: list[object] = []

    class FakeRequest:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(
        "http.server.ThreadingHTTPServer.process_request",
        lambda _server, request, _address: accepted.append(request),
    )
    first = FakeRequest()
    second = FakeRequest()
    server.process_request(first, ("10.0.0.1", 1))
    server.process_request(second, ("10.0.0.1", 2))

    assert accepted == [first]
    assert second.closed


def test_request_setup_applies_contract_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = object.__new__(StorageRequestHandler)

    class FakeConnection:
        timeout: int | None = None

        def settimeout(self, value: int) -> None:
            self.timeout = value

    connection = FakeConnection()
    handler.connection = connection
    handler.server = SimpleNamespace(
        contract=_contract(tmp_path, request_timeout_seconds=17)
    )
    monkeypatch.setattr(
        "http.server.BaseHTTPRequestHandler.setup", lambda _handler: None
    )

    handler.setup()

    assert connection.timeout == 17


def test_object_size_limit_is_enforced_before_reading(tmp_path: Path) -> None:
    store = _store(tmp_path, max_object_bytes=4)
    with pytest.raises(DataPlaneError) as too_large:
        store.store(
            "0" * 64,
            io.BytesIO(b"ignored"),
            content_length=5,
            operation_key="store-operation-large",
            envelope=_envelope(store, b"ignored"),
        )
    assert too_large.value.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
