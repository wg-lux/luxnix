from pathlib import Path

import pytest
import yaml

from lx_administration.storage.manager import (
    LEGACY_STORAGE_CONF_FILENAME,
    STORAGE_CONF_FILENAME,
    StorageManager,
    conf_filepath,
    generate_storage_directory_tree,
    initialize_storage_manager_from_env,
    legacy_conf_filepath,
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

    def test_generate_storage_directory_tree_creates_all_directories(
        self, tmp_path
    ):
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
