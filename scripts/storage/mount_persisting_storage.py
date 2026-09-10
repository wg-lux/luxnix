"""Mount the configured persisting-storage drive when required."""

import subprocess

from lx_administration.storage import (
    drive_with_serial_available,
    external_drive_requires_mount,
    initialize_storage_manager_from_env,
    mount_drive,
)


def main() -> int:
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
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Persisting-storage mount failed (exit {exc.returncode})."
            ) from exc
    else:
        print("Persisting storage drive is already mounted or not required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
