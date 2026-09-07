"""Fail-closed HTTPS data plane for dedicated LX-Annotate storage nodes.

The node stores opaque, content-addressed blobs.  Encryption and placement policy
belong to the hub; this process never receives an application master key.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import contextmanager
import fcntl
import hashlib
import heapq
import hmac
import json
import os
import re
import shutil
import ssl
import stat
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, BinaryIO, Final, Literal, Protocol
from urllib.parse import parse_qsl, urlsplit

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from .envelope import (
    ENVELOPE_HEADER,
    EnvelopeMetadata,
    load_recipient_private_key,
    recipient_key_id,
    verified_plaintext_chunks,
)
from .manager import StorageNodeContract

_DIGEST: Final = re.compile(r"^[0-9a-f]{64}$")
_OPERATION_KEY: Final = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
_CHUNK_SIZE: Final = 1024 * 1024
WIRE_CONTRACT_VERSION: Final = "lx-hub-storage-v1"
WIRE_CONTRACT_HEADER: Final = "X-LX-Storage-Contract"
_INVENTORY_DEFAULT_LIMIT: Final = 100
_INVENTORY_MAX_LIMIT: Final = 1000


def _decode_mountinfo_path(value: str) -> str:
    return re.sub(
        r"\\([0-7]{3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )


def _mounted_device_for(mount_point: Path) -> Path:
    """Resolve the kernel mount source for one exact mountpoint."""
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError("mount information is unavailable") from exc
    expected_mount = mount_point.resolve(strict=True)
    for line in lines:
        fields = line.split()
        try:
            separator = fields.index("-")
        except ValueError:
            continue
        if len(fields) <= separator + 2:
            continue
        candidate_mount = Path(_decode_mountinfo_path(fields[4]))
        try:
            candidate_mount = candidate_mount.resolve(strict=True)
        except OSError:
            continue
        if candidate_mount != expected_mount:
            continue
        source = _decode_mountinfo_path(fields[separator + 2]).split("[", 1)[0]
        if not source.startswith("/"):
            raise RuntimeError("protected mount source is not a device path")
        return Path(source).resolve(strict=True)
    raise RuntimeError("protected storage mount source is unavailable")


class DataPlaneError(Exception):
    """A request-safe error carrying an HTTP status."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


class BlobSource(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


@dataclass(frozen=True)
class Capacity:
    total_bytes: int
    free_bytes: int
    available_bytes: int
    used_percent: int
    accepting_writes: bool


@dataclass(frozen=True)
class JanitorResult:
    removed_incoming: int
    completed_quarantine: int
    removed_orphan_metadata: int
    quarantined_corrupt_receipts: int
    scanned_entries: int
    scan_limit_reached: bool


@dataclass(frozen=True)
class InventoryItem:
    ciphertext_sha256: str
    ciphertext_size: int
    plaintext_sha256: str
    plaintext_size: int
    recipient_key_id: str
    artifact_kind: Literal[
        "anonymized_video",
        "processed_report",
        "video_hls",
        "streamable_video",
        "sidecar",
        "manifest",
    ]


@dataclass(frozen=True)
class InventoryPage:
    items: tuple[InventoryItem, ...]
    next_cursor: str | None


def _encode_inventory_cursor(digest: str) -> str:
    raw = bytes.fromhex(digest)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_inventory_cursor(cursor: str) -> str:
    try:
        raw = base64.b64decode(
            cursor + "=" * (-len(cursor) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError, TypeError) as exc:
        raise DataPlaneError(HTTPStatus.BAD_REQUEST, "invalid inventory cursor") from exc
    if len(raw) != 32:
        raise DataPlaneError(HTTPStatus.BAD_REQUEST, "invalid inventory cursor")
    return raw.hex()


class BlobStore:
    """Content-addressed blob operations rooted in one protected mount."""

    def __init__(
        self,
        contract: StorageNodeContract,
        *,
        mount_guard: Callable[[Path], bool] = os.path.ismount,
        mount_source_resolver: Callable[[Path], Path] = _mounted_device_for,
    ) -> None:
        self.contract = contract
        self.root = contract.storage_root.resolve(strict=True)
        self._mount_guard = mount_guard
        self._mount_source_resolver = mount_source_resolver
        self.objects = self.root / "objects" / "sha256"
        self.incoming = self.root / ".incoming"
        self.quarantine = self.root / ".quarantine"
        self.receipts = self.root / ".operation-receipts"
        self.metadata = self.root / ".object-metadata"
        self.corrupt_receipts = self.root / ".corrupt-receipts"
        self.operation_lock_path = self.root / ".storage-operation.lock"
        self._operation_lock = threading.RLock()
        self._assert_protected_mount()
        for directory in (
            self.objects,
            self.incoming,
            self.quarantine,
            self.receipts,
            self.metadata,
            self.corrupt_receipts,
        ):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if directory.is_symlink():
                raise RuntimeError(
                    f"storage directory must not be a symlink: {directory}"
                )

    def _assert_protected_mount(self) -> None:
        if not self._mount_guard(self.root):
            raise DataPlaneError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "protected storage root is not a mounted filesystem",
            )
        try:
            actual_device = self._mount_source_resolver(self.root).resolve(strict=True)
            expected_device = self.contract.encrypted_device.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise DataPlaneError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "protected storage device identity is unavailable",
            ) from exc
        if actual_device != expected_device:
            raise DataPlaneError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "protected storage mount is backed by the wrong device",
            )

    @contextmanager
    def _exclusive_operations(self) -> Iterator[None]:
        """Serialize filesystem mutation across server and janitor processes."""
        with self._operation_lock:
            fd = os.open(self.operation_lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _preserve_corrupt_receipt(self, path: Path) -> bool:
        """Preserve one corrupt receipt without removing its fail-closed original."""
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                raw = os.read(fd, 1024 * 1024 + 1)
            finally:
                os.close(fd)
        except OSError:
            raw = b"unreadable"
        identity = hashlib.sha256(
            f"{path.parent.name}/{path.name}".encode() + b"\0" + raw
        ).hexdigest()
        destination = self.corrupt_receipts / identity
        try:
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        self._fsync_directory(self.corrupt_receipts)
        return True

    def run_janitor(
        self,
        *,
        minimum_age_seconds: int,
        max_entries: int = 10_000,
        now: float | None = None,
    ) -> JanitorResult:
        """Remove only provably stale or receipt-backed crash artifacts."""
        if minimum_age_seconds <= 0:
            raise ValueError("minimum_age_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._assert_protected_mount()
        cutoff = (time.time() if now is None else now) - minimum_age_seconds
        incoming = quarantined = metadata = corrupt = scanned = 0
        limit_reached = False

        def admit_entry() -> bool:
            nonlocal scanned, limit_reached
            if scanned >= max_entries:
                limit_reached = True
                return False
            scanned += 1
            return True

        with self._exclusive_operations():
            for path in self.incoming.iterdir():
                if not admit_entry():
                    break
                if (
                    path.is_file()
                    and not path.is_symlink()
                    and path.stat().st_mtime <= cutoff
                ):
                    path.unlink()
                    incoming += 1
            for path in self.quarantine.iterdir():
                if not admit_entry():
                    break
                match = re.fullmatch(r"([0-9a-f]{64})\.([0-9a-f]{64})", path.name)
                if (
                    match is None
                    or path.is_symlink()
                    or not path.is_file()
                    or path.stat().st_mtime > cutoff
                ):
                    continue
                digest, receipt_key = match.groups()
                receipt_path = self.receipts / "delete" / receipt_key
                try:
                    receipt = self._read_receipt(receipt_path)
                except DataPlaneError:
                    corrupt += int(self._preserve_corrupt_receipt(receipt_path))
                    continue
                if receipt == {"digest": digest} and self._verify_path(path, digest):
                    path.unlink()
                    quarantined += 1
            for prefix in self.metadata.iterdir():
                if not admit_entry():
                    break
                if prefix.is_symlink() or not prefix.is_dir():
                    continue
                for path in prefix.iterdir():
                    if not admit_entry():
                        break
                    digest = f"{prefix.name}{path.name}"
                    try:
                        self._read_receipt(path)
                    except DataPlaneError:
                        corrupt += int(self._preserve_corrupt_receipt(path))
                        continue
                    if (
                        _DIGEST.fullmatch(digest)
                        and path.is_file()
                        and not path.is_symlink()
                        and path.stat().st_mtime <= cutoff
                        and not self._object_path(digest).exists()
                        and not any(self.quarantine.glob(f"{digest}.*"))
                    ):
                        path.unlink()
                        self._fsync_directory(prefix)
                        metadata += 1
            for operation in self.receipts.iterdir():
                if not admit_entry():
                    break
                if operation.is_symlink() or not operation.is_dir():
                    continue
                for path in operation.iterdir():
                    if not admit_entry():
                        break
                    try:
                        self._read_receipt(path)
                    except DataPlaneError:
                        corrupt += int(self._preserve_corrupt_receipt(path))
            for directory in (self.incoming, self.quarantine, self.metadata):
                self._fsync_directory(directory)
        return JanitorResult(
            incoming,
            quarantined,
            metadata,
            corrupt,
            scanned,
            limit_reached,
        )

    @staticmethod
    def _validated_digest(digest: str) -> str:
        if not _DIGEST.fullmatch(digest):
            raise DataPlaneError(HTTPStatus.BAD_REQUEST, "invalid SHA-256 digest")
        return digest

    @staticmethod
    def _validated_operation_key(operation_key: str) -> str:
        if not _OPERATION_KEY.fullmatch(operation_key):
            raise DataPlaneError(
                HTTPStatus.BAD_REQUEST, "invalid or missing idempotency key"
            )
        return operation_key

    def _object_path(self, digest: str) -> Path:
        digest = self._validated_digest(digest)
        return self.objects / digest[:2] / digest[2:]

    def _receipt_path(self, operation: str, operation_key: str) -> Path:
        operation_key = self._validated_operation_key(operation_key)
        receipt_key = hashlib.sha256(operation_key.encode()).hexdigest()
        return self.receipts / operation / receipt_key

    def _read_receipt(self, path: Path) -> dict[str, Any] | None:
        try:
            flags = os.O_RDONLY | os.O_NOFOLLOW
            fd = os.open(path, flags)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise DataPlaneError(
                HTTPStatus.SERVICE_UNAVAILABLE, "operation receipt is unreadable"
            ) from exc
        try:
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except (OSError, ValueError) as exc:
            raise DataPlaneError(
                HTTPStatus.SERVICE_UNAVAILABLE, "operation receipt is unreadable"
            ) from exc
        if not isinstance(payload, dict):
            raise DataPlaneError(
                HTTPStatus.SERVICE_UNAVAILABLE, "operation receipt is invalid"
            )
        return payload

    def _write_receipt(self, path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        self._fsync_directory(path.parent)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def capacity(self) -> Capacity:
        self._assert_protected_mount()
        usage = shutil.disk_usage(self.root)
        used_percent = (100 * (usage.total - usage.free)) // usage.total
        available = max(0, usage.free - self.contract.capacity_reserve_bytes)
        accepting = used_percent < self.contract.capacity_stop_percent and available > 0
        return Capacity(
            total_bytes=usage.total,
            free_bytes=usage.free,
            available_bytes=available,
            used_percent=used_percent,
            accepting_writes=accepting,
        )

    def inventory(self, *, cursor: str | None, limit: int) -> InventoryPage:
        """Return one page while excluding concurrent object mutations and janitor work."""
        with self._exclusive_operations():
            return self._inventory_locked(cursor=cursor, limit=limit)

    def _inventory_locked(self, *, cursor: str | None, limit: int) -> InventoryPage:
        """Return a bounded, stable page derived only from stored object metadata."""
        self._assert_protected_mount()
        if limit < 1 or limit > _INVENTORY_MAX_LIMIT:
            raise DataPlaneError(
                HTTPStatus.BAD_REQUEST,
                f"inventory limit must be between 1 and {_INVENTORY_MAX_LIMIT}",
            )
        after_digest = _decode_inventory_cursor(cursor) if cursor is not None else ""

        def prefix_items(prefix: Path) -> Iterator[InventoryItem]:
            try:
                for path in prefix.iterdir():
                    digest = f"{prefix.name}{path.name}"
                    if digest <= after_digest or _DIGEST.fullmatch(digest) is None:
                        continue
                    stored = self._read_receipt(path)
                    if stored is None:
                        continue
                    declared_digest = stored.get("digest")
                    declared_size = stored.get("size")
                    if (
                        declared_digest != digest
                        or isinstance(declared_size, bool)
                        or not isinstance(declared_size, int)
                        or declared_size < 0
                        or not isinstance(stored.get("envelope"), dict)
                    ):
                        raise DataPlaneError(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            "object inventory metadata is invalid",
                        )
                    try:
                        envelope = EnvelopeMetadata.model_validate(stored["envelope"])
                    except ValueError as exc:
                        raise DataPlaneError(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            "object inventory metadata is invalid",
                        ) from exc
                    if envelope.node_id != self.contract.node_id:
                        raise DataPlaneError(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            "object inventory metadata targets another node",
                        )
                    try:
                        object_path = self._object_path(digest)
                        object_stat = object_path.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    except OSError as exc:
                        raise DataPlaneError(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            "object inventory entry is unavailable",
                        ) from exc
                    if not stat.S_ISREG(object_stat.st_mode):
                        raise DataPlaneError(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            "object inventory entry is not a regular file",
                        )
                    yield InventoryItem(
                        ciphertext_sha256=digest,
                        ciphertext_size=declared_size,
                        plaintext_sha256=envelope.plaintext_sha256,
                        plaintext_size=envelope.plaintext_size,
                        recipient_key_id=envelope.recipient_key_id,
                        artifact_kind=envelope.artifact_kind,
                    )
            except OSError as exc:
                raise DataPlaneError(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "object inventory is unavailable",
                ) from exc

        try:
            prefixes = sorted(self.metadata.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            raise DataPlaneError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "object inventory is unavailable",
            ) from exc
        selected: list[InventoryItem] = []
        for prefix in prefixes:
            if (
                prefix.is_symlink()
                or not prefix.is_dir()
                or re.fullmatch(r"[0-9a-f]{2}", prefix.name) is None
                or prefix.name < after_digest[:2]
            ):
                continue
            selected.extend(
                heapq.nsmallest(
                    limit + 1 - len(selected),
                    prefix_items(prefix),
                    key=lambda item: item.ciphertext_sha256,
                )
            )
            if len(selected) >= limit + 1:
                break
        page_items = tuple(selected[:limit])
        next_cursor = (
            _encode_inventory_cursor(page_items[-1].ciphertext_sha256)
            if len(selected) > limit
            else None
        )
        return InventoryPage(items=page_items, next_cursor=next_cursor)

    def store(
        self,
        digest: str,
        source: BlobSource,
        *,
        content_length: int,
        operation_key: str,
        envelope: EnvelopeMetadata,
    ) -> bool:
        """Store and fsync a blob. Return True only when a new object was created."""
        with self._exclusive_operations():
            return self._store_locked(
                digest,
                source,
                content_length=content_length,
                operation_key=operation_key,
                envelope=envelope,
            )

    def _store_locked(
        self,
        digest: str,
        source: BlobSource,
        *,
        content_length: int,
        operation_key: str,
        envelope: EnvelopeMetadata,
    ) -> bool:
        self._assert_protected_mount()
        digest = self._validated_digest(digest)
        self._validated_operation_key(operation_key)
        self._validate_envelope_recipient(envelope)
        if content_length < 0 or content_length > self.contract.max_object_bytes:
            raise DataPlaneError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "object too large"
            )
        capacity = self.capacity()
        if not capacity.accepting_writes or content_length > capacity.available_bytes:
            raise DataPlaneError(
                HTTPStatus.INSUFFICIENT_STORAGE, "storage admission is closed"
            )

        receipt_path = self._receipt_path("store", operation_key)
        receipt = self._read_receipt(receipt_path)
        expected_receipt = {
            "digest": digest,
            "size": content_length,
            "envelope": envelope.model_dump(mode="json"),
        }
        if receipt is not None:
            if receipt != expected_receipt:
                raise DataPlaneError(
                    HTTPStatus.CONFLICT, "idempotency key was used for another object"
                )
            metadata_path = self.metadata / digest[:2] / digest[2:]
            if self._read_receipt(metadata_path) == expected_receipt and self.verify(
                digest, expected_size=content_length
            ):
                return False
            raise DataPlaneError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "stored-object receipt exists but the object is unavailable",
            )

        destination = self._object_path(digest)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = (
            self.incoming
            / f"{digest}.{hashlib.sha256(operation_key.encode()).hexdigest()}"
        )
        hasher = hashlib.sha256()
        written = 0
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                while written < content_length:
                    chunk = source.read(min(_CHUNK_SIZE, content_length - written))
                    if not chunk:
                        break
                    written += len(chunk)
                    hasher.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if written != content_length or not hmac.compare_digest(
                hasher.hexdigest(), digest
            ):
                raise DataPlaneError(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "content length or SHA-256 digest mismatch",
                )
            if destination.exists():
                if not self.verify(digest, expected_size=content_length):
                    raise DataPlaneError(
                        HTTPStatus.CONFLICT,
                        "existing object does not match requested content",
                    )
                metadata_path = self.metadata / digest[:2] / digest[2:]
                existing_metadata = self._read_receipt(metadata_path)
                if (
                    existing_metadata is not None
                    and existing_metadata != expected_receipt
                ):
                    raise DataPlaneError(
                        HTTPStatus.CONFLICT,
                        "existing object envelope metadata does not match",
                    )
                created = False
            else:
                os.replace(temp, destination)
                self._fsync_directory(destination.parent)
                created = True
            metadata_path = self.metadata / digest[:2] / digest[2:]
            self._write_receipt(metadata_path, expected_receipt)
            self._write_receipt(receipt_path, expected_receipt)
            return created
        finally:
            temp.unlink(missing_ok=True)

    def _validate_envelope_recipient(self, envelope: EnvelopeMetadata) -> None:
        if envelope.node_id != self.contract.node_id:
            raise DataPlaneError(
                HTTPStatus.BAD_REQUEST, "envelope targets a different storage node"
            )
        self._recipient_private_key(envelope)

    def _recipient_private_key(self, envelope: EnvelopeMetadata) -> X25519PrivateKey:
        loaded_identity = False
        for identity_path in self.contract.recipient_identity_paths():
            try:
                private_key = load_recipient_private_key(identity_path)
            except (OSError, ValueError):
                continue
            loaded_identity = True
            if hmac.compare_digest(
                recipient_key_id(private_key), envelope.recipient_key_id
            ):
                return private_key
        if loaded_identity:
            raise DataPlaneError(
                HTTPStatus.BAD_REQUEST,
                "envelope recipient does not match an active storage-node identity",
            )
        raise DataPlaneError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "storage recipient identities are unavailable",
        )

    def recipient_key_ids(self) -> tuple[str, ...]:
        """Return the exact active/retiring recipient set for rotation telemetry."""
        identities: list[str] = []
        for identity_path in self.contract.recipient_identity_paths():
            try:
                identities.append(
                    recipient_key_id(load_recipient_private_key(identity_path))
                )
            except (OSError, ValueError) as exc:
                raise DataPlaneError(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "storage recipient identities are unavailable",
                ) from exc
        if len(identities) != len(set(identities)):
            raise DataPlaneError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "storage recipient identities are ambiguous",
            )
        return tuple(identities)

    def open_blob(self, digest: str) -> tuple[BinaryIO, int]:
        self._assert_protected_mount()
        path = self._object_path(digest)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError as exc:
            raise DataPlaneError(HTTPStatus.NOT_FOUND, "object not found") from exc
        except OSError as exc:
            raise DataPlaneError(
                HTTPStatus.CONFLICT, "object is not a regular file"
            ) from exc
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            os.close(fd)
            raise DataPlaneError(HTTPStatus.CONFLICT, "object is not a regular file")
        return os.fdopen(fd, "rb"), file_stat.st_size

    def verify(self, digest: str, *, expected_size: int | None = None) -> bool:
        try:
            stream, size = self.open_blob(digest)
        except DataPlaneError as exc:
            if exc.status is HTTPStatus.NOT_FOUND:
                return False
            raise
        with stream:
            if expected_size is not None and size != expected_size:
                return False
            hasher = hashlib.sha256()
            while chunk := stream.read(_CHUNK_SIZE):
                hasher.update(chunk)
        return hmac.compare_digest(hasher.hexdigest(), digest)

    def open_verified_blob(self, digest: str) -> tuple[BinaryIO, int]:
        """Open a blob only after checking that its bytes still match its key."""
        stream, size = self.open_blob(digest)
        hasher = hashlib.sha256()
        while chunk := stream.read(_CHUNK_SIZE):
            hasher.update(chunk)
        if not hmac.compare_digest(hasher.hexdigest(), digest):
            stream.close()
            raise DataPlaneError(HTTPStatus.CONFLICT, "object integrity check failed")
        stream.seek(0)
        return stream, size

    def open_verified_plaintext(
        self, digest: str
    ) -> tuple[BinaryIO, int, str, Iterator[bytes]]:
        """Open verified ciphertext and return authenticated plaintext chunks."""

        stream, _ciphertext_size = self.open_verified_blob(digest)
        metadata_path = self.metadata / digest[:2] / digest[2:]
        stored = self._read_receipt(metadata_path)
        if stored is None or not isinstance(stored.get("envelope"), dict):
            stream.close()
            raise DataPlaneError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "object envelope metadata is unavailable",
            )
        try:
            envelope = EnvelopeMetadata.model_validate(stored["envelope"])
            self._validate_envelope_recipient(envelope)
            private_key = self._recipient_private_key(envelope)
            chunks = verified_plaintext_chunks(stream, envelope, private_key)
            # Prime the generator so authentication and the first full verification
            # pass happen before the HTTP response starts disclosing plaintext.
            first = next(chunks, b"")
        except (OSError, ValueError) as exc:
            stream.close()
            raise DataPlaneError(
                HTTPStatus.CONFLICT, "object envelope authentication failed"
            ) from exc

        def complete_chunks() -> Iterator[bytes]:
            try:
                if first:
                    yield first
                yield from chunks
            finally:
                stream.close()

        return (
            stream,
            envelope.plaintext_size,
            envelope.plaintext_sha256,
            complete_chunks(),
        )

    def verify_envelope(self, digest: str) -> dict[str, object]:
        """Verify ciphertext, key wrapping, authentication tag, size, and digest."""

        try:
            _stream, size, plaintext_digest, chunks = self.open_verified_plaintext(
                digest
            )
        except DataPlaneError as exc:
            if exc.status is HTTPStatus.NOT_FOUND:
                return {
                    "ciphertext_sha256": digest,
                    "plaintext_sha256": None,
                    "plaintext_size": None,
                    "valid": False,
                }
            raise
        for _chunk in chunks:
            pass
        return {
            "ciphertext_sha256": digest,
            "plaintext_sha256": plaintext_digest,
            "plaintext_size": size,
            "valid": True,
        }

    def delete(self, digest: str, *, operation_key: str, precondition: str) -> bool:
        """Quarantine then unlink an exactly identified object."""
        with self._exclusive_operations():
            return self._delete_locked(
                digest,
                operation_key=operation_key,
                precondition=precondition,
            )

    def _delete_locked(
        self, digest: str, *, operation_key: str, precondition: str
    ) -> bool:
        self._assert_protected_mount()
        digest = self._validated_digest(digest)
        self._validated_operation_key(operation_key)
        if not hmac.compare_digest(precondition, digest):
            raise DataPlaneError(
                HTTPStatus.PRECONDITION_FAILED, "delete digest precondition failed"
            )
        receipt_path = self._receipt_path("delete", operation_key)
        source = self._object_path(digest)
        quarantine = (
            self.quarantine
            / f"{digest}.{hashlib.sha256(operation_key.encode()).hexdigest()}"
        )
        receipt = self._read_receipt(receipt_path)
        if receipt is not None:
            if receipt != {"digest": digest}:
                raise DataPlaneError(
                    HTTPStatus.CONFLICT, "idempotency key was used for another object"
                )
            if quarantine.exists():
                if not self._verify_path(quarantine, digest):
                    raise DataPlaneError(
                        HTTPStatus.CONFLICT,
                        "quarantined delete state is inconsistent",
                    )
                quarantine.unlink()
                self._fsync_directory(self.quarantine)
            return False
        if quarantine.exists():
            if source.exists() or not self._verify_path(quarantine, digest):
                raise DataPlaneError(
                    HTTPStatus.CONFLICT, "quarantined delete state is inconsistent"
                )
            self._write_receipt(receipt_path, {"digest": digest})
            quarantine.unlink()
            self._fsync_directory(self.quarantine)
            return False
        if source.exists() and not self._verify_path(source, digest):
            raise DataPlaneError(
                HTTPStatus.CONFLICT, "object integrity check failed before delete"
            )
        try:
            os.replace(source, quarantine)
        except FileNotFoundError as exc:
            raise DataPlaneError(HTTPStatus.NOT_FOUND, "object not found") from exc
        self._fsync_directory(source.parent)
        self._fsync_directory(self.quarantine)
        self._write_receipt(receipt_path, {"digest": digest})
        quarantine.unlink()
        self._fsync_directory(self.quarantine)
        return True

    @staticmethod
    def _verify_path(path: Path, digest: str) -> bool:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            return False
        hasher = hashlib.sha256()
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return False
            while chunk := stream.read(_CHUNK_SIZE):
                hasher.update(chunk)
        return hmac.compare_digest(hasher.hexdigest(), digest)


def _peer_identities(certificate: Mapping[str, Any]) -> set[str]:
    """Return exact DNS/URI SAN values; deliberately never trust CN fallback."""
    identities: set[str] = set()
    for kind, value in certificate.get("subjectAltName", ()):
        if kind in {"DNS", "URI"} and isinstance(value, str):
            identities.add(value)
    return identities


class StorageHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, contract: StorageNodeContract, store: BlobStore) -> None:
        self.contract = contract
        self.store = store
        self._request_slots = threading.BoundedSemaphore(
            contract.max_concurrent_requests
        )
        self.request_queue_size = contract.max_concurrent_requests
        super().__init__(
            (contract.listen_address, contract.port), StorageRequestHandler
        )

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._request_slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class StorageRequestHandler(BaseHTTPRequestHandler):
    server: StorageHTTPServer
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(self.server.contract.request_timeout_seconds)

    def _authenticate(self, operation: str) -> None:
        if self.client_address[0] not in self.server.contract.allowed_hub_addresses:
            raise DataPlaneError(HTTPStatus.FORBIDDEN, "source address is not allowed")
        if not isinstance(self.connection, ssl.SSLSocket):
            raise DataPlaneError(HTTPStatus.FORBIDDEN, "mutual TLS is required")
        certificate = self.connection.getpeercert()
        if not certificate:
            raise DataPlaneError(HTTPStatus.FORBIDDEN, "client certificate is required")
        identities = _peer_identities(certificate)
        allowed_identities = identities & set(
            self.server.contract.allowed_hub_identities
        )
        if not allowed_identities:
            raise DataPlaneError(
                HTTPStatus.FORBIDDEN, "client certificate identity is not allowed"
            )
        if len(allowed_identities) != 1:
            raise DataPlaneError(
                HTTPStatus.FORBIDDEN,
                "client certificate has ambiguous allowed identities",
            )
        if not any(
            operation in self.server.contract.hub_identity_operations[identity]
            for identity in allowed_identities
        ):
            raise DataPlaneError(
                HTTPStatus.FORBIDDEN,
                "client certificate identity is not authorized for this operation",
            )

    def _object_digest(self, suffix: str = "") -> str:
        match = re.fullmatch(rf"/v1/objects/([0-9a-f]{{64}}){suffix}", self.path)
        if not match:
            raise DataPlaneError(HTTPStatus.NOT_FOUND, "unknown endpoint")
        return match.group(1)

    def _send_json(self, status: HTTPStatus, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header(WIRE_CONTRACT_HEADER, WIRE_CONTRACT_VERSION)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, operation: str, action: Callable[[], None]) -> None:
        try:
            self._authenticate(operation)
            action()
        except DataPlaneError as exc:
            self.close_connection = True
            self._send_json(exc.status, {"error": str(exc)})
        except Exception:
            self.close_connection = True
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal error"}
            )

    def do_GET(self) -> None:  # noqa: N802
        request_path = urlsplit(self.path).path
        if request_path == "/v1/health":
            operation = "health"
        elif request_path == "/v1/capacity":
            operation = "capacity"
        elif request_path == "/v1/inventory":
            operation = "inventory"
        elif request_path.endswith("/plaintext"):
            operation = "fetch_plaintext"
        else:
            operation = "fetch_ciphertext"
        self._dispatch(operation, self._get)

    def _get(self) -> None:
        if self.path == "/v1/health":
            capacity = self.server.store.capacity()
            self._send_json(
                HTTPStatus.OK,
                {
                    "contract_version": WIRE_CONTRACT_VERSION,
                    "node_id": self.server.contract.node_id,
                    "status": "ready" if capacity.accepting_writes else "read_only",
                    "accepting_writes": capacity.accepting_writes,
                    "used_percent": capacity.used_percent,
                    "available_bytes": capacity.available_bytes,
                    "recipient_key_ids": self.server.store.recipient_key_ids(),
                },
            )
            return
        if self.path == "/v1/capacity":
            self._send_json(HTTPStatus.OK, vars(self.server.store.capacity()))
            return
        parsed = urlsplit(self.path)
        if parsed.path == "/v1/inventory":
            try:
                pairs = parse_qsl(
                    parsed.query,
                    keep_blank_values=True,
                    strict_parsing=True,
                )
            except ValueError as exc:
                raise DataPlaneError(
                    HTTPStatus.BAD_REQUEST, "invalid inventory query"
                ) from exc
            parameters: dict[str, str] = {}
            for name, value in pairs:
                if name not in {"cursor", "limit"} or name in parameters:
                    raise DataPlaneError(
                        HTTPStatus.BAD_REQUEST, "invalid inventory query"
                    )
                parameters[name] = value
            cursor = parameters.get("cursor")
            if cursor == "":
                raise DataPlaneError(
                    HTTPStatus.BAD_REQUEST, "invalid inventory cursor"
                )
            try:
                limit = int(parameters.get("limit", str(_INVENTORY_DEFAULT_LIMIT)))
            except ValueError as exc:
                raise DataPlaneError(
                    HTTPStatus.BAD_REQUEST, "invalid inventory limit"
                ) from exc
            page = self.server.store.inventory(cursor=cursor, limit=limit)
            self._send_json(
                HTTPStatus.OK,
                {
                    "contract_version": WIRE_CONTRACT_VERSION,
                    "node_id": self.server.contract.node_id,
                    "items": [vars(item) for item in page.items],
                    "next_cursor": page.next_cursor,
                },
            )
            return
        plaintext_match = re.fullmatch(
            r"/v1/objects/([0-9a-f]{64})/plaintext", self.path
        )
        if plaintext_match:
            digest = plaintext_match.group(1)
            _stream, size, plaintext_digest, chunks = (
                self.server.store.open_verified_plaintext(digest)
            )
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header(WIRE_CONTRACT_HEADER, WIRE_CONTRACT_VERSION)
            self.send_header("Content-Length", str(size))
            self.send_header("X-Plaintext-SHA256", plaintext_digest)
            self.end_headers()
            for chunk in chunks:
                self.wfile.write(chunk)
            return
        digest = self._object_digest()
        stream, size = self.server.store.open_verified_blob(digest)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header(WIRE_CONTRACT_HEADER, WIRE_CONTRACT_VERSION)
        self.send_header("Content-Length", str(size))
        self.send_header("ETag", f'"{digest}"')
        self.end_headers()
        with stream:
            shutil.copyfileobj(stream, self.wfile, _CHUNK_SIZE)

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("store", self._put)

    def _put(self) -> None:
        digest = self._object_digest()
        if self.headers.get("Transfer-Encoding"):
            raise DataPlaneError(
                HTTPStatus.BAD_REQUEST, "transfer encoding is not supported"
            )
        if self.headers.get("X-Content-SHA256", "") != digest:
            raise DataPlaneError(HTTPStatus.BAD_REQUEST, "digest header mismatch")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError as exc:
            raise DataPlaneError(
                HTTPStatus.LENGTH_REQUIRED, "content length required"
            ) from exc
        try:
            envelope = EnvelopeMetadata.from_header(
                self.headers.get(ENVELOPE_HEADER, "")
            )
        except ValueError as exc:
            raise DataPlaneError(
                HTTPStatus.BAD_REQUEST, "invalid or missing envelope metadata"
            ) from exc
        created = self.server.store.store(
            digest,
            self.rfile,
            content_length=length,
            operation_key=self.headers.get("Idempotency-Key", ""),
            envelope=envelope,
        )
        self.close_connection = True
        self._send_json(
            HTTPStatus.CREATED if created else HTTPStatus.OK,
            {
                "ciphertext_sha256": digest,
                "ciphertext_size": length,
                "plaintext_sha256": envelope.plaintext_sha256,
                "plaintext_size": envelope.plaintext_size,
                "recipient_key_id": envelope.recipient_key_id,
                "created": created,
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("verify", self._post)

    def _post(self) -> None:
        digest = self._object_digest("/verify")
        self._send_json(
            HTTPStatus.OK,
            self.server.store.verify_envelope(digest),
        )

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("delete", self._delete)

    def _delete(self) -> None:
        digest = self._object_digest()
        precondition = self.headers.get("If-Match", "").strip('"')
        deleted = self.server.store.delete(
            digest,
            operation_key=self.headers.get("Idempotency-Key", ""),
            precondition=precondition,
        )
        self._send_json(HTTPStatus.OK, {"deleted": deleted, "digest": digest})

    def log_message(self, format: str, *args: object) -> None:
        # Avoid request headers and object identifiers reaching default stderr logs.
        return


def _validate_identity_files(contract: StorageNodeContract) -> None:
    for path in (
        contract.tls_ca_file,
        contract.tls_cert_file,
        contract.tls_key_file,
        *contract.recipient_identity_paths(),
    ):
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"identity file is absent, empty, or a symlink: {path}")
    for private_path in (
        contract.tls_key_file,
        *contract.recipient_identity_paths(),
    ):
        if private_path.stat().st_mode & 0o007:
            raise RuntimeError(
                "private identity must not be accessible to other users: "
                f"{private_path}"
            )
    recipient_ids: list[str] = []
    for identity_path in contract.recipient_identity_paths():
        try:
            recipient_ids.append(
                recipient_key_id(load_recipient_private_key(identity_path))
            )
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                "recipient identity must contain an X25519 PEM private key"
            ) from exc
    if len(recipient_ids) != len(set(recipient_ids)):
        raise RuntimeError("recipient identity files must contain distinct keys")


def _build_tls_context(contract: StorageNodeContract) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(contract.tls_ca_file))
    context.load_cert_chain(
        certfile=str(contract.tls_cert_file), keyfile=str(contract.tls_key_file)
    )
    return context


def serve(contract: StorageNodeContract) -> None:
    _validate_identity_files(contract)
    context = _build_tls_context(contract)
    store = BlobStore(contract)
    server = StorageHTTPServer(contract, store)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="LX-Annotate protected storage node")
    parser.add_argument(
        "action", nargs="?", choices=("serve", "janitor"), default="serve"
    )
    parser.add_argument("--minimum-age-seconds", type=int, default=86_400)
    parser.add_argument("--max-entries", type=int, default=10_000)
    args = parser.parse_args()
    contract = StorageNodeContract.from_environment()
    if args.action == "janitor":
        result = BlobStore(contract).run_janitor(
            minimum_age_seconds=args.minimum_age_seconds,
            max_entries=args.max_entries,
        )
        print(
            json.dumps(
                {
                    "contract_version": WIRE_CONTRACT_VERSION,
                    "event": "storage_janitor_completed",
                    "node_id": contract.node_id,
                    **vars(result),
                },
                sort_keys=True,
            )
        )
        return
    serve(contract)


if __name__ == "__main__":
    main()
