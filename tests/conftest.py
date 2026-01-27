"""Pytest configuration for loading test environment variables."""

import os
from pathlib import Path
import pytest


@pytest.fixture(scope="function")
def load_test_env_vars() -> None:
    """Fixture to load test environment variables before each test."""
    tmp_path = Path("./test_wd").resolve()
    wd = tmp_path / "working_dir"
    wd.mkdir(parents=True, exist_ok=True)

    cfg_dir = tmp_path / "config_dir"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    storage_fast_root = tmp_path / "data" / "storage-fast"
    storage_fast_root.mkdir(parents=True, exist_ok=True)
    storage_persisting_root = tmp_path / "data" / "storage-persisting"
    storage_persisting_root.mkdir(parents=True, exist_ok=True)

    os.environ["HOME_DIR"] = tmp_path.as_posix()
    os.environ["CONFIG_DIR"] = cfg_dir.as_posix()
    os.environ["WORKING_DIR"] = wd.as_posix()
    os.environ["STORAGE_PERSISTING_EXTERNAL_DRIVE"] = "false"
    os.environ["STORAGE_FAST_ROOT"] = storage_fast_root.as_posix()
    os.environ["STORAGE_PERSISTING_HDD_ID"] = ""
    os.environ["STORAGE_PERSISTING_MOUNT_POINT"] = storage_persisting_root.as_posix()


# ENV_FILE = Path(__file__).parent / "test-env.env"


# def _load_env_file() -> None:
#     """Load key/value pairs from tests/test-env.env into os.environ."""

#     if not ENV_FILE.is_file():
#         return

#     for line in ENV_FILE.read_text().splitlines():
#         line = line.strip()
#         if not line or line.startswith("#"):
#             continue
#         if "=" not in line:
#             continue

#         key, value = line.split("=", 1)
#         os.environ[key.strip()] = value.strip()


# def pytest_configure() -> None:
#     _load_env_file()
