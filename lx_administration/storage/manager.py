import ipaddress
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, TypedDict
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lx_administration.yaml import dump_yaml, load_unique_yaml_file

STORAGE_CONF_FILENAME = "storage_manager.yml"
LEGACY_STORAGE_CONF_FILENAME = "storage_manager.yaml"


class StorageNodeContract(BaseModel):
    """Versioned deployment contract shared with the LuxNix storage-node role.

    This model intentionally carries paths to identity material, never secret values
    or an application master key. The data-plane application remains responsible for
    mTLS peer authorization and for per-transfer envelope encryption.
    """

    schema_version: Literal[1] = 1
    deployment_role: Literal["storage_node"] = "storage_node"
    node_id: str = Field(min_length=1)
    storage_root: Path
    encrypted_device: Path
    listen_address: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    allowed_hub_addresses: list[str] = Field(min_length=1)
    allowed_hub_identities: list[str] = Field(min_length=1)
    hub_identity_operations: dict[
        str,
        set[
            Literal[
                "health",
                "capacity",
                "inventory",
                "store",
                "fetch_ciphertext",
                "fetch_plaintext",
                "verify",
                "delete",
            ]
        ],
    ]
    tls_ca_file: Path
    tls_cert_file: Path
    tls_key_file: Path
    recipient_private_identity_file: Path | None = Field(
        default=None,
        description="X25519 PEM private key used only for per-transfer key unwrap",
    )
    recipient_private_identity_files: list[Path] = Field(
        default_factory=list,
        description=(
            "Current and retiring X25519 private identities accepted during "
            "key rotation"
        ),
    )
    capacity_warning_percent: int = Field(default=75, ge=1, le=99)
    capacity_stop_percent: int = Field(default=90, ge=2, le=100)
    capacity_recovery_percent: int = Field(default=70, ge=0, le=98)
    capacity_reserve_bytes: int = Field(default=10 * 1024**3, gt=0)
    max_object_bytes: int = Field(default=1024**4, gt=0)
    max_concurrent_requests: int = Field(default=16, ge=1, le=256)
    request_timeout_seconds: int = Field(default=120, ge=1, le=3600)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "StorageNodeContract":
        """Load the exact versioned contract rendered by LuxNix."""
        values = os.environ if environment is None else environment

        def required(name: str) -> str:
            value = str(values.get(name, "")).strip()
            if not value:
                raise ValueError(f"{name} is required")
            return value

        return cls.model_validate(
            {
                "schema_version": int(required("HUB_STORAGE_SCHEMA_VERSION")),
                "deployment_role": required("HUB_STORAGE_DEPLOYMENT_ROLE"),
                "node_id": required("HUB_STORAGE_NODE_ID"),
                "storage_root": required("HUB_STORAGE_ROOT"),
                "encrypted_device": required("HUB_STORAGE_ENCRYPTED_DEVICE"),
                "listen_address": required("HUB_STORAGE_LISTEN_ADDRESS"),
                "port": required("HUB_STORAGE_PORT"),
                "allowed_hub_addresses": [
                    address.strip()
                    for address in required("HUB_STORAGE_ALLOWED_HUB_ADDRESSES").split(
                        ","
                    )
                    if address.strip()
                ],
                "allowed_hub_identities": [
                    identity.strip()
                    for identity in required(
                        "HUB_STORAGE_ALLOWED_HUB_IDENTITIES"
                    ).split(",")
                    if identity.strip()
                ],
                "hub_identity_operations": json.loads(
                    required("HUB_STORAGE_HUB_IDENTITY_OPERATIONS")
                ),
                "tls_ca_file": required("HUB_STORAGE_TLS_CA_FILE"),
                "tls_cert_file": required("HUB_STORAGE_TLS_CERT_FILE"),
                "tls_key_file": required("HUB_STORAGE_TLS_KEY_FILE"),
                "recipient_private_identity_file": str(
                    values.get("HUB_STORAGE_RECIPIENT_PRIVATE_IDENTITY_FILE", "")
                ).strip()
                or None,
                "recipient_private_identity_files": [
                    path.strip()
                    for path in str(
                        values.get("HUB_STORAGE_RECIPIENT_PRIVATE_IDENTITY_FILES", "")
                    ).split(",")
                    if path.strip()
                ],
                "capacity_warning_percent": required(
                    "HUB_STORAGE_CAPACITY_WARNING_PERCENT"
                ),
                "capacity_stop_percent": required("HUB_STORAGE_CAPACITY_STOP_PERCENT"),
                "capacity_recovery_percent": required(
                    "HUB_STORAGE_CAPACITY_RECOVERY_PERCENT"
                ),
                "capacity_reserve_bytes": required(
                    "HUB_STORAGE_CAPACITY_RESERVE_BYTES"
                ),
                "max_object_bytes": required("HUB_STORAGE_MAX_OBJECT_BYTES"),
                "max_concurrent_requests": required(
                    "HUB_STORAGE_MAX_CONCURRENT_REQUESTS"
                ),
                "request_timeout_seconds": required(
                    "HUB_STORAGE_REQUEST_TIMEOUT_SECONDS"
                ),
            }
        )

    @model_validator(mode="after")
    def validate_fail_closed_contract(self) -> "StorageNodeContract":
        if len(self.node_id) > 253:
            raise ValueError("storage node identity must be at most 253 characters")
        if self.listen_address in {"0.0.0.0", "::"}:
            raise ValueError("storage node must not bind a wildcard address")
        listen_ip = ipaddress.ip_address(self.listen_address)
        if not listen_ip.is_private or listen_ip.is_loopback:
            raise ValueError(
                "storage node listen_address must be a private non-loopback IP"
            )
        for address in self.allowed_hub_addresses:
            hub_ip = ipaddress.ip_address(address)
            if not hub_ip.is_private or hub_ip.is_unspecified:
                raise ValueError("allowed hub addresses must be private IP addresses")
        if any(
            not identity or "," in identity or len(identity) > 253
            for identity in self.allowed_hub_identities
        ):
            raise ValueError(
                "allowed hub identities must be non-empty exact SAN values"
            )
        if set(self.hub_identity_operations) != set(self.allowed_hub_identities):
            raise ValueError(
                "hub identity operation keys must exactly match allowed identities"
            )
        if any(not operations for operations in self.hub_identity_operations.values()):
            raise ValueError("every allowed hub identity needs at least one operation")
        if not (
            self.capacity_recovery_percent
            < self.capacity_warning_percent
            < self.capacity_stop_percent
        ):
            raise ValueError(
                "capacity thresholds must satisfy recovery < warning < stop"
            )
        recipient_paths = self.recipient_identity_paths()
        if not recipient_paths:
            raise ValueError("at least one recipient private identity is required")
        if len(recipient_paths) != len(set(recipient_paths)):
            raise ValueError("recipient private identity paths must be unique")
        if len(recipient_paths) > 3:
            raise ValueError("at most three recipient identities may overlap")
        path_fields = (
            self.storage_root,
            self.encrypted_device,
            self.tls_ca_file,
            self.tls_cert_file,
            self.tls_key_file,
            *recipient_paths,
        )
        if not all(path.is_absolute() for path in path_fields):
            raise ValueError("storage and identity paths must be absolute")
        return self

    def recipient_identity_paths(self) -> tuple[Path, ...]:
        values = list(self.recipient_private_identity_files)
        if self.recipient_private_identity_file is not None:
            values.insert(0, self.recipient_private_identity_file)
        return tuple(values)


class HubStorageNodePeerContract(BaseModel):
    """One storage-node identity authorized by the central hub."""

    node_key: str = Field(min_length=1, max_length=253)
    display_name: str = Field(min_length=1, max_length=253)
    failure_domain: str = Field(min_length=1, max_length=128)
    residency_key: str = Field(min_length=1, max_length=128)
    placement_weight: int = Field(gt=0)
    artifact_kinds: set[
        Literal[
            "anonymized_video",
            "processed_report",
            "video_hls",
            "streamable_video",
            "sidecar",
            "manifest",
        ]
    ] = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    ca_certificate_file: Path
    client_certificate_file: Path
    client_key_file: Path
    recipient_public_key_file: Path = Field(
        description="X25519 PEM public key used for per-transfer key wrapping"
    )

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_private_peer(self) -> "HubStorageNodePeerContract":
        parsed = urlparse(self.endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "storage endpoint must be a host-only HTTPS URL with an explicit port"
            )
        try:
            endpoint_ip = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            if not parsed.hostname.endswith((".intern", ".internal", ".aglnet")):
                raise ValueError(
                    "storage endpoint hostname must use an approved private suffix"
                ) from None
        else:
            if not endpoint_ip.is_private or endpoint_ip.is_unspecified:
                raise ValueError("storage endpoint must use a private IP address")
        paths = (
            self.ca_certificate_file,
            self.client_certificate_file,
            self.client_key_file,
            self.recipient_public_key_file,
        )
        if not all(path.is_absolute() for path in paths):
            raise ValueError("hub storage credential paths must be absolute")
        return self


class HubStorageClientContract(BaseModel):
    """Versioned central-hub view of authorized storage-node peers."""

    schema_version: Literal[1] = 1
    deployment_role: Literal["central_hub"] = "central_hub"
    nodes: list[HubStorageNodePeerContract] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_unique_node_keys(self) -> "HubStorageClientContract":
        node_keys = [node.node_key for node in self.nodes]
        if len(node_keys) != len(set(node_keys)):
            raise ValueError("hub storage node_key values must be unique")
        endpoints = [node.endpoint.rstrip("/") for node in self.nodes]
        if len(endpoints) != len(set(endpoints)):
            raise ValueError("hub storage endpoints must be unique")
        return self

    @classmethod
    def load_file(cls, path: Path) -> "HubStorageClientContract":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.model_validate(payload)


class StoragePaths(TypedDict):
    data: Path
    backups: Path
    logs: Path
    temp: Path
    configs: Path
    video_dir: Path
    image_dir: Path
    document_dir: Path


def initialize_storage_manager_from_env() -> "StorageManager":
    """Initialize StorageManager from environment variables."""
    storage_manager = StorageManager()
    storage_manager.save_to_file()
    return storage_manager


def conf_filepath(storage_fast_root: Path) -> Path:
    dirtree = generate_storage_directory_tree(storage_fast_root)
    return dirtree["configs"] / STORAGE_CONF_FILENAME


def legacy_conf_filepath(storage_fast_root: Path) -> Path:
    """Return the pre-migration `.yaml` configuration path."""
    dirtree = generate_storage_directory_tree(storage_fast_root)
    return dirtree["configs"] / LEGACY_STORAGE_CONF_FILENAME


def serialize_path(path: Path | None) -> str | None:
    """Serialize a Path object to its POSIX string representation.

    Args:
        path (Path | None): The Path object to serialize.

    Returns:
        str | None: The POSIX representation, or None when no path was given.
    """
    return path.as_posix() if path is not None else None


def _expand_env_template(value: str) -> str:
    """Expand `{VAR}` placeholders using environment variables."""

    class _Env(dict[Any, Any]):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    expanded = value.format_map(_Env(os.environ))
    if "{" in expanded or "}" in expanded:
        raise ValueError(f"Unresolved placeholder in value: {expanded}")
    return expanded


def _default_home_dir() -> Path:
    home_dir = os.getenv("HOME_DIR")
    if home_dir:
        return Path(home_dir).expanduser().resolve()
    raise ValueError("HOME_DIR environment variable is not set.")


def _default_working_dir() -> Path:
    working_dir = os.getenv("WORKING_DIR")
    if working_dir:
        return Path(_expand_env_template(working_dir)).expanduser().resolve()
    return Path.cwd().expanduser().resolve()


def _default_storage_persisting_external_drive() -> bool:
    external_drive = os.getenv("STORAGE_PERSISTING_EXTERNAL_DRIVE")
    if external_drive is not None:
        return external_drive.lower() in ("true", "1", "yes")
    return False


def _default_storage_persisting_hdd_id() -> str | None:
    hdd_id = os.getenv("STORAGE_PERSISTING_HDD_ID")
    return hdd_id if hdd_id else None


def _default_storage_fast_dir_tree() -> StoragePaths:
    storage_fast_root = os.getenv("STORAGE_FAST_ROOT")
    if storage_fast_root:
        expanded = _expand_env_template(storage_fast_root)
        base_path = Path(expanded).expanduser().resolve()
    else:
        raise ValueError("STORAGE_FAST_ROOT environment variable is not set.")
    return generate_storage_directory_tree(base_path)


def _default_storage_persisting_dir_tree() -> StoragePaths:
    storage_persisting_root = os.getenv("STORAGE_PERSISTING_MOUNT_POINT")
    if storage_persisting_root:
        expanded = _expand_env_template(storage_persisting_root)
        base_path = Path(expanded).expanduser().resolve()
        return generate_storage_directory_tree(base_path)
    raise ValueError("STORAGE_PERSISTING_MOUNT_POINT environment variable is not set.")


def generate_storage_directory_tree(
    base_path: Path, create: bool = False
) -> StoragePaths:
    """Generate a standard directory tree for storage management.

    Args:
        base_path (Path): The base path where the directory tree will be created.
    """
    directories = StoragePaths(
        data=base_path / "data",
        video_dir=base_path / "data" / "videos",
        image_dir=base_path / "data" / "images",
        document_dir=base_path / "data" / "documents",
        backups=base_path / "backups",
        logs=base_path / "logs",
        temp=base_path / "temp",
        configs=base_path / "configs",
    )

    if create:
        for directory in directories.values():
            if not isinstance(directory, Path):
                raise TypeError("storage directory entries must be paths")
            directory.mkdir(parents=True, exist_ok=True)

    return directories


class StorageManager(BaseModel):
    home_dir: Path = Field(
        default_factory=_default_home_dir,
        description="The home directory for storage management.",
    )
    working_dir: Path = Field(
        default_factory=_default_working_dir,
        description="The current working directory.",
    )
    storage_persisting_external_drive: bool = Field(
        default_factory=_default_storage_persisting_external_drive,
        description=(
            "Flag indicating whether persisting storage uses an external drive."
        ),
    )

    storage_persisting_hdd_id: str | None = Field(
        default_factory=_default_storage_persisting_hdd_id,
        description="Identifier for the persisting HDD.",
    )

    storage_root: Path = Field(
        default_factory=lambda: Path(os.getenv("STORAGE_ROOT", "/mnt/luxnix_storage"))
        .expanduser()
        .resolve(),
        description="Root path for storage management.",
    )

    storage_persisting_mount_point: Path = Field(
        default_factory=lambda: Path(
            os.getenv("STORAGE_PERSISTING_MOUNT_POINT", "/mnt/luxnix_persisting_data")
        )
        .expanduser()
        .resolve(),
        description="Mount point for the persisting storage.",
    )

    storage_fast_dir_tree: StoragePaths = Field(
        default_factory=_default_storage_fast_dir_tree,
        description="Directory tree for fast storage.",
    )

    storage_persisting_dir_tree: StoragePaths = Field(
        default_factory=_default_storage_persisting_dir_tree,
        description="Directory tree for persisting storage, if applicable.",
    )

    storage_persisting_initialized: bool = Field(
        default=False,
        description="Flag indicating if persisting storage has been initialized.",
    )

    model_config = ConfigDict(
        # 1. Strips leading/trailing whitespace automatically ("  val  " -> "val")
        str_strip_whitespace=True,
        # 2. Rejects extra fields not defined in the model (Security/Strictness)
        extra="forbid",
        # 3. Validates default values (ensures your defaults aren't broken)
        validate_default=True,
        # 4. Allows population by alias (e.g. accepting "camelCase" input)
        populate_by_name=True,
        ser_json_timedelta="iso8601",
        ser_json_temporal="iso8601",
        val_temporal_unit="seconds",
        ser_json_bytes="utf8",
        val_json_bytes="utf8",
        ser_json_inf_nan="strings",
        regex_engine="rust-regex",
        validate_by_name=False,
        serialize_by_alias=False,
        json_encoders={Path: serialize_path},
        revalidate_instances="always",
        arbitrary_types_allowed=False,
    )

    @classmethod
    def get_or_create_instance(cls, storage_fast_root: Path) -> "StorageManager":
        """Load canonical or legacy configuration, otherwise create one."""
        canonical_path = conf_filepath(storage_fast_root)
        legacy_path = legacy_conf_filepath(storage_fast_root)
        for config_path in (canonical_path, legacy_path):
            if not config_path.is_file():
                continue
            data = load_unique_yaml_file(config_path)
            if not isinstance(data, dict):
                raise ValueError(f"Expected a YAML mapping in {config_path}")
            return cls.model_validate(data)

        return initialize_storage_manager_from_env()

    @property
    def config_dir(self) -> Path:
        return self.storage_fast_dir_tree["configs"]

    @property
    def config_filepath(self) -> Path:
        return self.config_dir / STORAGE_CONF_FILENAME

    @property
    def storage_persisting_available(self) -> bool:
        """Return whether configured persistent storage is usable."""
        if self.storage_persisting_external_drive:
            return (
                self.storage_persisting_mount_point.is_mount()
                and self.storage_persisting_hdd_id is not None
            )
        return self.storage_persisting_mount_point.exists()

    def save_to_file(self, filepath: Path | None = None) -> None:
        """Save the StorageManager configuration to a file.

        Args:
            filepath: File path to save, or the canonical config path by default.
        """
        if filepath is None:
            filepath = self.config_filepath
        dump: dict[str, Any] = self.model_dump(mode="json")

        dump_yaml(dump, filepath)
