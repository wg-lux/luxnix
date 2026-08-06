"""Public, lazily loaded storage-management API."""

from typing import TYPE_CHECKING

from .._lazy_exports import public_names, resolve_lazy_export

if TYPE_CHECKING:
    from .manager import (
        StorageManager,
        conf_filepath,
        generate_storage_directory_tree,
        initialize_storage_manager_from_env,
        legacy_conf_filepath,
    )
    from .mounting import (
        drive_with_serial_available,
        external_drive_requires_mount,
        find_device_by_serial,
        mount_drive,
        unmount_drive,
    )

__all__ = [
    "StorageManager",
    "conf_filepath",
    "legacy_conf_filepath",
    "generate_storage_directory_tree",
    "initialize_storage_manager_from_env",
    "external_drive_requires_mount",
    "find_device_by_serial",
    "drive_with_serial_available",
    "mount_drive",
    "unmount_drive",
]

_EXPORTS = {
    "StorageManager": (".manager", "StorageManager"),
    "conf_filepath": (".manager", "conf_filepath"),
    "legacy_conf_filepath": (".manager", "legacy_conf_filepath"),
    "generate_storage_directory_tree": (
        ".manager",
        "generate_storage_directory_tree",
    ),
    "initialize_storage_manager_from_env": (
        ".manager",
        "initialize_storage_manager_from_env",
    ),
    "external_drive_requires_mount": (
        ".mounting",
        "external_drive_requires_mount",
    ),
    "find_device_by_serial": (".mounting", "find_device_by_serial"),
    "drive_with_serial_available": (".mounting", "drive_with_serial_available"),
    "mount_drive": (".mounting", "mount_drive"),
    "unmount_drive": (".mounting", "unmount_drive"),
}


def __getattr__(name: str) -> object:
    """Resolve storage helpers without eagerly importing Pydantic models."""
    return resolve_lazy_export(
        name,
        package_name=__name__,
        exports=_EXPORTS,
        namespace=globals(),
    )


def __dir__() -> list[str]:
    return public_names(globals(), _EXPORTS)
