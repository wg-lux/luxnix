from lx_administration.storage.manager import (
    # StorageManager,
    initialize_storage_manager_from_env,
)
from lx_administration.storage.mounting import (
    drive_with_serial_available,
    external_drive_requires_mount,
    mount_drive,
)

if __name__ == "__main__":
    sm = initialize_storage_manager_from_env()
    if external_drive_requires_mount(sm):
        device = drive_with_serial_available(sm)
        if device is None:
            raise RuntimeError(
                "Persisting storage drive with the configured serial is not available."
            )
        try:
            mount_drive(
                device,
                sm.storage_persisting_mount_point,
                filesystem="ext4",
            )
        except Exception as exc:
            # Surface the underlying mount error for troubleshooting
            if hasattr(exc, "stdout") or hasattr(exc, "stderr"):
                print("mount stdout:\n", getattr(exc, "stdout", ""))
                print("mount stderr:\n", getattr(exc, "stderr", ""))
            raise
    else:
        print("Persisting storage drive is already mounted or not required.")
    #
