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

        mount_drive(
            device,
            sm.storage_persisting_mount_point,
            filesystem="ext4",
        )
    else:
        print("Persisting storage drive is already mounted or not required.")
    #
