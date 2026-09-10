"""Versioned storage-transfer envelope consumed by the storage node.

The hub encrypts each artifact with a fresh AES-256 key and wraps that key to
the storage node's X25519 recipient identity.  The long-lived application
master key is neither an input nor part of this protocol.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import BaseModel, ConfigDict, Field, field_validator

ENVELOPE_PROFILE = "x25519-hkdf-sha256-aes256gcm-v1"
ENVELOPE_HEADER = "X-Envelope-Metadata"
_CHUNK_SIZE = 1024 * 1024


def _decode(value: str, *, expected_size: int, field_name: str) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field_name} must be base64url encoded") from exc
    if len(decoded) != expected_size:
        raise ValueError(f"{field_name} must decode to {expected_size} bytes")
    return decoded


class EnvelopeMetadata(BaseModel):
    """Authenticated envelope metadata transported as one bounded HTTP header."""

    schema_version: Literal[1] = 1
    profile: Literal["x25519-hkdf-sha256-aes256gcm-v1"] = (
        "x25519-hkdf-sha256-aes256gcm-v1"
    )
    node_id: str = Field(min_length=1, max_length=253)
    artifact_kind: Literal[
        "anonymized_video",
        "processed_report",
        "video_hls",
        "streamable_video",
        "sidecar",
        "manifest",
    ]
    recipient_key_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    plaintext_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plaintext_size: int = Field(gt=0)
    ephemeral_public_key: str
    wrap_salt: str
    wrap_nonce: str
    wrapped_data_encryption_key: str
    payload_nonce: str
    payload_tag: str

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    @field_validator("ephemeral_public_key")
    @classmethod
    def validate_ephemeral_key(cls, value: str) -> str:
        _decode(value, expected_size=32, field_name="ephemeral_public_key")
        return value

    @field_validator("wrap_salt")
    @classmethod
    def validate_wrap_salt(cls, value: str) -> str:
        _decode(value, expected_size=16, field_name="wrap_salt")
        return value

    @field_validator("wrap_nonce", "payload_nonce")
    @classmethod
    def validate_nonce(cls, value: str) -> str:
        _decode(value, expected_size=12, field_name="nonce")
        return value

    @field_validator("wrapped_data_encryption_key")
    @classmethod
    def validate_wrapped_key(cls, value: str) -> str:
        _decode(value, expected_size=48, field_name="wrapped_data_encryption_key")
        return value

    @field_validator("payload_tag")
    @classmethod
    def validate_payload_tag(cls, value: str) -> str:
        _decode(value, expected_size=16, field_name="payload_tag")
        return value

    def authenticated_context(self) -> bytes:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "profile": self.profile,
                "node_id": self.node_id,
                "artifact_kind": self.artifact_kind,
                "recipient_key_id": self.recipient_key_id,
                "plaintext_sha256": self.plaintext_sha256,
                "plaintext_size": self.plaintext_size,
                "ephemeral_public_key": self.ephemeral_public_key,
                "wrap_salt": self.wrap_salt,
                "payload_nonce": self.payload_nonce,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def to_header(self) -> str:
        encoded = base64.urlsafe_b64encode(
            self.model_dump_json(by_alias=False).encode("utf-8")
        )
        return encoded.rstrip(b"=").decode("ascii")

    @classmethod
    def from_header(cls, value: str) -> "EnvelopeMetadata":
        if not value or len(value) > 4096:
            raise ValueError("envelope metadata header is absent or too large")
        try:
            payload = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except (ValueError, TypeError) as exc:
            raise ValueError("envelope metadata header must be base64url") from exc
        return cls.model_validate_json(payload)


def load_recipient_private_key(path: Path) -> X25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, X25519PrivateKey):
        raise ValueError("recipient identity must be an X25519 PEM private key")
    return key


def recipient_key_id(private_key: X25519PrivateKey) -> str:
    public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(public).hexdigest()


def unwrap_data_encryption_key(
    metadata: EnvelopeMetadata, private_key: X25519PrivateKey
) -> bytes:
    if recipient_key_id(private_key) != metadata.recipient_key_id:
        raise ValueError("envelope recipient does not match this storage node")
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey

    ephemeral = X25519PublicKey.from_public_bytes(
        _decode(
            metadata.ephemeral_public_key,
            expected_size=32,
            field_name="ephemeral_public_key",
        )
    )
    shared = private_key.exchange(ephemeral)
    wrapping_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_decode(metadata.wrap_salt, expected_size=16, field_name="wrap_salt"),
        info=b"lx-hub-storage-envelope-wrap-v1",
    ).derive(shared)
    return AESGCM(wrapping_key).decrypt(
        _decode(metadata.wrap_nonce, expected_size=12, field_name="wrap_nonce"),
        _decode(
            metadata.wrapped_data_encryption_key,
            expected_size=48,
            field_name="wrapped_data_encryption_key",
        ),
        metadata.authenticated_context(),
    )


def _decrypt_chunks(
    source: BinaryIO, metadata: EnvelopeMetadata, data_encryption_key: bytes
) -> Iterator[bytes]:
    decryptor = Cipher(
        algorithms.AES(data_encryption_key),
        modes.GCM(
            _decode(
                metadata.payload_nonce,
                expected_size=12,
                field_name="payload_nonce",
            ),
            _decode(metadata.payload_tag, expected_size=16, field_name="payload_tag"),
        ),
    ).decryptor()
    decryptor.authenticate_additional_data(metadata.authenticated_context())
    while chunk := source.read(_CHUNK_SIZE):
        plaintext = decryptor.update(chunk)
        if plaintext:
            yield plaintext
    final = decryptor.finalize()
    if final:
        yield final


def verified_plaintext_chunks(
    source: BinaryIO,
    metadata: EnvelopeMetadata,
    private_key: X25519PrivateKey,
) -> Iterator[bytes]:
    """Verify the complete envelope before yielding plaintext from a second pass."""

    data_encryption_key = unwrap_data_encryption_key(metadata, private_key)
    digest = hashlib.sha256()
    size = 0
    try:
        for chunk in _decrypt_chunks(source, metadata, data_encryption_key):
            digest.update(chunk)
            size += len(chunk)
    except InvalidTag as exc:
        raise ValueError("envelope authentication failed") from exc
    if (
        size != metadata.plaintext_size
        or digest.hexdigest() != metadata.plaintext_sha256
    ):
        raise ValueError("envelope plaintext size or digest mismatch")
    source.seek(0)
    try:
        yield from _decrypt_chunks(source, metadata, data_encryption_key)
    except InvalidTag as exc:
        raise ValueError("envelope changed after verification") from exc


__all__ = [
    "ENVELOPE_HEADER",
    "ENVELOPE_PROFILE",
    "EnvelopeMetadata",
    "load_recipient_private_key",
    "recipient_key_id",
    "verified_plaintext_chunks",
]
