import json
from pathlib import Path

import pytest
import yaml

from lx_administration.storage.manager import (
    HubStorageClientContract,
    LEGACY_STORAGE_CONF_FILENAME,
    STORAGE_CONF_FILENAME,
    StorageNodeContract,
    StorageManager,
    conf_filepath,
    generate_storage_directory_tree,
    initialize_storage_manager_from_env,
    legacy_conf_filepath,
)


def _storage_node_contract(**overrides) -> StorageNodeContract:
    values = {
        "node_id": "storage-01",
        "storage_root": "/mnt/lx-annotate-storage",
        "encrypted_device": "/dev/mapper/lx-annotate-storage",
        "listen_address": "172.16.255.31",
        "port": 9443,
        "allowed_hub_addresses": ["172.16.255.14"],
        "allowed_hub_identities": ["spiffe://endoreg/hub/primary"],
        "hub_identity_operations": {
            "spiffe://endoreg/hub/primary": {
                "health",
                "capacity",
                "store",
                "fetch_ciphertext",
                "fetch_plaintext",
                "verify",
                "delete",
            }
        },
        "tls_ca_file": "/run/credentials/storage-ca.pem",
        "tls_cert_file": "/run/credentials/storage-cert.pem",
        "tls_key_file": "/run/credentials/storage-key.pem",
        "recipient_private_identity_file": "/run/credentials/storage-recipient.key",
    }
    values.update(overrides)
    return StorageNodeContract(**values)


def test_storage_node_contract_has_explicit_role_and_capacity_defaults() -> None:
    contract = _storage_node_contract()

    assert contract.schema_version == 1
    assert contract.deployment_role == "storage_node"
    assert contract.capacity_recovery_percent < contract.capacity_warning_percent
    assert contract.capacity_warning_percent < contract.capacity_stop_percent


def test_storage_node_contract_loads_the_luxnix_environment() -> None:
    contract = _storage_node_contract()
    environment = {
        "HUB_STORAGE_SCHEMA_VERSION": "1",
        "HUB_STORAGE_DEPLOYMENT_ROLE": "storage_node",
        "HUB_STORAGE_NODE_ID": contract.node_id,
        "HUB_STORAGE_ROOT": str(contract.storage_root),
        "HUB_STORAGE_ENCRYPTED_DEVICE": str(contract.encrypted_device),
        "HUB_STORAGE_LISTEN_ADDRESS": contract.listen_address,
        "HUB_STORAGE_PORT": str(contract.port),
        "HUB_STORAGE_ALLOWED_HUB_ADDRESSES": ",".join(contract.allowed_hub_addresses),
        "HUB_STORAGE_ALLOWED_HUB_IDENTITIES": ",".join(contract.allowed_hub_identities),
        "HUB_STORAGE_HUB_IDENTITY_OPERATIONS": json.dumps(
            {
                identity: sorted(operations)
                for identity, operations in contract.hub_identity_operations.items()
            }
        ),
        "HUB_STORAGE_TLS_CA_FILE": str(contract.tls_ca_file),
        "HUB_STORAGE_TLS_CERT_FILE": str(contract.tls_cert_file),
        "HUB_STORAGE_TLS_KEY_FILE": str(contract.tls_key_file),
        "HUB_STORAGE_RECIPIENT_PRIVATE_IDENTITY_FILE": str(
            contract.recipient_private_identity_file
        ),
        "HUB_STORAGE_CAPACITY_WARNING_PERCENT": str(contract.capacity_warning_percent),
        "HUB_STORAGE_CAPACITY_STOP_PERCENT": str(contract.capacity_stop_percent),
        "HUB_STORAGE_CAPACITY_RECOVERY_PERCENT": str(
            contract.capacity_recovery_percent
        ),
        "HUB_STORAGE_CAPACITY_RESERVE_BYTES": str(contract.capacity_reserve_bytes),
        "HUB_STORAGE_MAX_OBJECT_BYTES": str(contract.max_object_bytes),
        "HUB_STORAGE_MAX_CONCURRENT_REQUESTS": str(contract.max_concurrent_requests),
        "HUB_STORAGE_REQUEST_TIMEOUT_SECONDS": str(contract.request_timeout_seconds),
    }

    assert StorageNodeContract.from_environment(environment) == contract


def test_storage_node_contract_loads_a_rotation_keyring() -> None:
    environment = {
        "HUB_STORAGE_SCHEMA_VERSION": "1",
        "HUB_STORAGE_DEPLOYMENT_ROLE": "storage_node",
        "HUB_STORAGE_NODE_ID": "storage-01",
        "HUB_STORAGE_ROOT": "/mnt/storage",
        "HUB_STORAGE_ENCRYPTED_DEVICE": "/dev/mapper/storage",
        "HUB_STORAGE_LISTEN_ADDRESS": "10.0.0.2",
        "HUB_STORAGE_PORT": "9443",
        "HUB_STORAGE_ALLOWED_HUB_ADDRESSES": "10.0.0.1",
        "HUB_STORAGE_ALLOWED_HUB_IDENTITIES": "spiffe://endoreg/hub/primary",
        "HUB_STORAGE_HUB_IDENTITY_OPERATIONS": json.dumps(
            {"spiffe://endoreg/hub/primary": ["health"]}
        ),
        "HUB_STORAGE_TLS_CA_FILE": "/run/ca",
        "HUB_STORAGE_TLS_CERT_FILE": "/run/cert",
        "HUB_STORAGE_TLS_KEY_FILE": "/run/key",
        "HUB_STORAGE_RECIPIENT_PRIVATE_IDENTITY_FILES": "/run/old.pem,/run/new.pem",
        "HUB_STORAGE_CAPACITY_WARNING_PERCENT": "75",
        "HUB_STORAGE_CAPACITY_STOP_PERCENT": "90",
        "HUB_STORAGE_CAPACITY_RECOVERY_PERCENT": "70",
        "HUB_STORAGE_CAPACITY_RESERVE_BYTES": "1024",
        "HUB_STORAGE_MAX_OBJECT_BYTES": "4096",
        "HUB_STORAGE_MAX_CONCURRENT_REQUESTS": "8",
        "HUB_STORAGE_REQUEST_TIMEOUT_SECONDS": "60",
    }
    contract = StorageNodeContract.from_environment(environment)
    assert contract.recipient_identity_paths() == (
        Path("/run/old.pem"),
        Path("/run/new.pem"),
    )


def test_hub_storage_contract_uses_node_key_and_rejects_public_endpoint(
    tmp_path: Path,
) -> None:
    contract_path = tmp_path / "nodes.json"
    contract_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "deployment_role": "central_hub",
                "nodes": [
                    {
                        "node_key": "storage-01",
                        "display_name": "Storage 01",
                        "failure_domain": "rack-a",
                        "residency_key": "de",
                        "placement_weight": 100,
                        "artifact_kinds": ["anonymized_video", "sidecar"],
                        "endpoint": "https://storage-01.aglnet:9443",
                        "ca_certificate_file": "/run/ca",
                        "client_certificate_file": "/run/cert",
                        "client_key_file": "/run/key",
                        "recipient_public_key_file": "/run/recipient.pub",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = HubStorageClientContract.load_file(contract_path)
    assert loaded.nodes[0].node_key == "storage-01"

    payload = loaded.model_dump(mode="json")
    payload["nodes"][0]["endpoint"] = "https://gs-01.intern:9443"
    assert HubStorageClientContract.model_validate(payload).nodes[0].node_key == (
        "storage-01"
    )

    payload = loaded.model_dump(mode="json")
    payload["nodes"][0]["endpoint"] = "https://example.com:9443"
    with pytest.raises(ValueError, match="private"):
        HubStorageClientContract.model_validate(payload)


def test_storage_node_contract_is_part_of_public_storage_api() -> None:
    from lx_administration.storage import StorageNodeContract as PublicContract

    assert PublicContract is StorageNodeContract


@pytest.mark.parametrize("listen_address", ["0.0.0.0", "::"])
def test_storage_node_contract_rejects_public_wildcard_bind(
    listen_address: str,
) -> None:
    with pytest.raises(ValueError, match="must not bind a wildcard"):
        _storage_node_contract(listen_address=listen_address)


def test_storage_node_contract_rejects_unsafe_threshold_order() -> None:
    with pytest.raises(ValueError, match="recovery < warning < stop"):
        _storage_node_contract(
            capacity_recovery_percent=80,
            capacity_warning_percent=75,
        )


def test_storage_node_contract_rejects_master_key_and_unknown_fields() -> None:
    with pytest.raises(ValueError, match="[Ee]xtra inputs are not permitted"):
        _storage_node_contract(application_master_key_file="/run/master-key")


def test_storage_node_contract_bounds_recipient_rotation_overlap() -> None:
    with pytest.raises(ValueError, match="at most three"):
        _storage_node_contract(
            recipient_private_identity_file=None,
            recipient_private_identity_files=[
                "/run/recipient-1",
                "/run/recipient-2",
                "/run/recipient-3",
                "/run/recipient-4",
            ],
        )


def test_hub_storage_contract_rejects_ambiguous_duplicate_endpoint() -> None:
    peer = {
        "display_name": "Storage",
        "failure_domain": "rack-a",
        "residency_key": "de",
        "placement_weight": 100,
        "artifact_kinds": ["anonymized_video"],
        "endpoint": "https://storage-01.aglnet:9443",
        "ca_certificate_file": "/run/ca",
        "client_certificate_file": "/run/cert",
        "client_key_file": "/run/key",
        "recipient_public_key_file": "/run/recipient.pub",
    }
    with pytest.raises(ValueError, match="endpoints must be unique"):
        HubStorageClientContract.model_validate(
            {
                "nodes": [
                    {"node_key": "storage-01", **peer},
                    {"node_key": "storage-02", **peer},
                ]
            }
        )


class TestStorageManager:
    def test_missing_home_dir_fails_clearly(
        self, load_test_env_vars: None, monkeypatch
    ):
        monkeypatch.delenv("HOME_DIR")

        with pytest.raises(ValueError, match="HOME_DIR environment variable"):
            StorageManager()

    def test_initialize_storage_manager_from_env(self, load_test_env_vars: None):
        storage_manager = initialize_storage_manager_from_env()
        assert isinstance(storage_manager, StorageManager)
        assert storage_manager.storage_persisting_available is True
        assert storage_manager.config_filepath.name == "storage_manager.yml"
        assert storage_manager.config_filepath.is_file()

    def test_missing_working_dir_uses_current_directory(
        self, load_test_env_vars: None, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("WORKING_DIR")
        monkeypatch.chdir(tmp_path)

        storage_manager = StorageManager()

        assert storage_manager.working_dir == tmp_path

    def test_missing_internal_storage_is_unavailable(
        self, load_test_env_vars: None, tmp_path
    ):
        storage_manager = StorageManager(
            storage_persisting_external_drive=False,
            storage_persisting_mount_point=tmp_path / "missing",
        )

        assert storage_manager.storage_persisting_available is False

    def test_generate_storage_directory_tree_creates_all_directories(self, tmp_path):
        directories = generate_storage_directory_tree(tmp_path, create=True)

        assert all(directory.is_dir() for directory in directories.values())

    def test_canonical_storage_config_roundtrip(self, load_test_env_vars: None):
        storage_manager = initialize_storage_manager_from_env()
        storage_fast_root = storage_manager.storage_fast_dir_tree["data"].parent

        loaded = StorageManager.get_or_create_instance(storage_fast_root)

        assert loaded == storage_manager
        assert conf_filepath(storage_fast_root).name == STORAGE_CONF_FILENAME

    def test_legacy_yaml_config_remains_readable(self, load_test_env_vars: None):
        storage_manager = StorageManager()
        storage_fast_root = storage_manager.storage_fast_dir_tree["data"].parent
        conf_filepath(storage_fast_root).unlink(missing_ok=True)
        legacy_path = legacy_conf_filepath(storage_fast_root)
        storage_manager.save_to_file(legacy_path)

        loaded = StorageManager.get_or_create_instance(storage_fast_root)

        assert loaded == storage_manager
        assert legacy_path.name == LEGACY_STORAGE_CONF_FILENAME
        assert not conf_filepath(storage_fast_root).exists()

    def test_legacy_config_rejects_duplicate_keys_with_path(
        self, load_test_env_vars: None
    ):
        storage_fast_root = Path("test_wd/data/storage-fast").resolve()
        conf_filepath(storage_fast_root).unlink(missing_ok=True)
        legacy_path = legacy_conf_filepath(storage_fast_root)
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text("home_dir: first\nhome_dir: second\n", encoding="utf-8")

        with pytest.raises(yaml.YAMLError, match="duplicate key 'home_dir'") as error:
            StorageManager.get_or_create_instance(storage_fast_root)

        assert str(legacy_path) in str(error.value)
