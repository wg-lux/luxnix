from lx_administration.storage.manager import (
    StorageManager,
    initialize_storage_manager_from_env,
)

# from pathlib import Path


class TestStorageManager:
    def test_initialize_storage_manager_from_env(self, load_test_env_vars: None):

        storage_manager = initialize_storage_manager_from_env()
        assert isinstance(storage_manager, StorageManager)

        assert storage_manager.storage_persisting_available is True
