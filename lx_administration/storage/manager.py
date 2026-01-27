from pydantic import BaseModel, Field, ConfigDict
import os
from pathlib import Path
from typing import Any, Optional, TypedDict, cast
import yaml

STORAGE_CONF_FILENAME = "storage_manager.yaml"


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


def serialize_path(path: Path | None) -> str | None:
    """Serialize a Path object to its POSIX string representation.

    Args:
        path (Path | None): The Path object to serialize.

    Returns:
        str | None: The POSIX string representation of the path, or None if the input is None.
    """
    if path is not None:
        return path.as_posix()
    return None


def _expand_env_template(value: str) -> str:
    """Expand `{VAR}` placeholders using environment variables."""

    class _Env(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    expanded = value.format_map(_Env(os.environ))
    if "{" in expanded or "}" in expanded:
        raise ValueError(f"Unresolved placeholder in value: {expanded}")
    return expanded


def _default_home_dir() -> Path:
    home_dir = str(os.getenv("HOME_DIR"))
    if home_dir:
        return Path(home_dir).expanduser().resolve()
    else:
        raise ValueError("HOME_DIR environment variable is not set.")


def _default_working_dir() -> Path:
    working_dir = str(os.getenv("WORKING_DIR"))
    if working_dir:
        return Path(_expand_env_template(working_dir)).expanduser().resolve()
    return Path.cwd().expanduser().resolve()


def _default_storage_persitinve_external_drive() -> bool:
    external_drive = os.getenv("STORAGE_PERSISTING_EXTERNAL_DRIVE")
    if external_drive is not None:
        return external_drive.lower() in ("true", "1", "yes")
    return False


def _default_storage_persisting_hdd_id() -> Optional[str]:
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
        **{
            "data": base_path / "data",
            "video_dir": base_path / "data" / "videos",
            "image_dir": base_path / "data" / "images",
            "document_dir": base_path / "data" / "documents",
            "backups": base_path / "backups",
            "logs": base_path / "logs",
            "temp": base_path / "temp",
            "configs": base_path / "configs",
        }
    )
    path_list = cast(list[Path], [dir_path for dir_path in directories.values()])

    if create:
        for p in path_list:
            p.mkdir(parents=True, exist_ok=True)

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
        default_factory=_default_storage_persitinve_external_drive,
        description="Flag to indicate if an external drive is used for persisting storage.",
    )

    storage_persisting_hdd_id: Optional[str] = Field(
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
        """Get or create a singleton instance of StorageManager."""
        _path = conf_filepath(storage_fast_root)
        if _path.exists():
            # load from file
            with open(_path, "r") as f:
                return cls.model_validate(f.read())

        else:
            return initialize_storage_manager_from_env()

    @property
    def config_dir(self) -> Path:
        return self.storage_fast_dir_tree["configs"]

    @property
    def config_filepath(self) -> Path:
        return self.config_dir / STORAGE_CONF_FILENAME

    @property
    def storage_persisting_available(self) -> bool:
        """Check if the persisting storage is mounted."""
        external_drive = self.storage_persisting_external_drive
        is_mount = self.storage_persisting_mount_point.is_mount()
        serial = self.storage_persisting_hdd_id

        # External drive case
        if external_drive:
            if not is_mount:
                return False
            if serial is None:
                return False
            return True

        # non-external drive case
        else:
            assert self.storage_persisting_mount_point.exists()
            return True

    def save_to_file(self, filepath: Optional[Path] = None) -> None:
        """Save the StorageManager configuration to a file.

        Args:
            filepath (Optional[Path]): The file path to save the configuration.
                                       If None, uses the default config_filepath.
        """
        if filepath is None:
            filepath = self.config_filepath
        dump: dict[str, Any] = self.model_dump(mode="json")

        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            yaml.safe_dump(  # type: ignore
                dump, f, encoding="utf-8", allow_unicode=True, indent=2, sort_keys=False
            )
