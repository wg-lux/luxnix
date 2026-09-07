{ lib }:
{
  entrypoint =
    {
      cfg,
      pkgs,
      adminUserName,
      storagePersistingMountPoint,
      ...
    }:
    {
      config = {
        security.sudo.extraRules = [
          {
            users = [ adminUserName ];
            commands = [
              {
                command = "${pkgs.util-linux}/bin/mount";
                options = [ "NOPASSWD" ];
              }
              {
                command = "${pkgs.util-linux}/bin/umount";
                options = [ "NOPASSWD" ];
              }
            ];
          }
        ];

        systemd.services.endoreg-mount-persisting-storage =
          lib.mkIf (cfg.paths.storagePersistingEnable && cfg.paths.storagePersistingIsExternalDrive)
            {
              description = "Mount verified host-owned endoreg persisting storage";
              serviceConfig = {
                Type = "oneshot";
                User = "root";
                Environment = [
                  "STORAGE_PERSISTING_EXTERNAL_DRIVE=${
                    if cfg.paths.storagePersistingIsExternalDrive then "true" else "false"
                  }"
                  "STORAGE_PERSISTING_MOUNT_POINT=${toString storagePersistingMountPoint}"
                  "STORAGE_PERSISTING_HDD_ID=${
                    if cfg.paths.storagePersistingDeviceId == null then "" else cfg.paths.storagePersistingDeviceId
                  }"
                  "STORAGE_PERSISTING_HDD_PART=${cfg.paths.storagePersistingDevicePart}"
                ];
                ExecStartPre = [ ];
                ExecStart = pkgs.writeShellScript "mount-persisting-storage-service" ''
                  set -euo pipefail

                  storage_persisting_external_drive="''${STORAGE_PERSISTING_EXTERNAL_DRIVE:-false}"
                  storage_persisting_mount_point="''${STORAGE_PERSISTING_MOUNT_POINT:-}"
                  storage_persisting_hdd_id="''${STORAGE_PERSISTING_HDD_ID:-}"
                  storage_persisting_hdd_part="''${STORAGE_PERSISTING_HDD_PART:-part1}"

                  # if STORAGE_PERSISTING_EXTERNAL_DRIVE is not true, exit
                  if [ "$storage_persisting_external_drive" != "true" ]; then
                    echo "STORAGE_PERSISTING_EXTERNAL_DRIVE is not true; skipping mount"
                    exit 0

                  fi

                  if [ -z "$storage_persisting_mount_point" ]; then
                    echo "ERROR: STORAGE_PERSISTING_MOUNT_POINT is not set"
                    exit 1
                  fi

                  if [ -z "$storage_persisting_hdd_id" ]; then
                    echo "ERROR: STORAGE_PERSISTING_HDD_ID is not set"
                    exit 1
                  fi

                  # Always verify the configured device, including an existing
                  # mount: a USB reconnect can leave a stale device number mounted.
                  DEV_BASE="/dev/disk/by-id/$storage_persisting_hdd_id"
                  DEV_PATH="$DEV_BASE-$storage_persisting_hdd_part"
                  if [ ! -b "$DEV_PATH" ]; then
                    echo "ERROR: Configured storage block device $DEV_PATH is unavailable"
                    exit 1
                  fi
                  expected_device_number=$(lsblk -dnro MAJ:MIN "$DEV_PATH")
                  if [ -z "$expected_device_number" ]; then
                    echo "ERROR: Cannot determine configured storage device identity"
                    exit 1
                  fi
                  if ! mountpoint -q "$storage_persisting_mount_point"; then
                    echo "Mounting persisting storage drive $DEV_PATH to $storage_persisting_mount_point"
                    mount "$DEV_PATH" "$storage_persisting_mount_point"
                  fi
                  mounted_device_number=$(findmnt -n -o MAJ:MIN --mountpoint "$storage_persisting_mount_point")
                  if [ "$mounted_device_number" != "$expected_device_number" ]; then
                    echo "ERROR: Persisting storage mount does not match the configured block device; preserve the mount for operator inspection"
                    exit 1
                  fi
                  echo "Verified persisting storage mount successfully"
                '';
              };
              path = [
                pkgs.coreutils
                pkgs.util-linux
              ];
            };

        systemd.timers.endoreg-mount-persisting-storage =
          lib.mkIf (cfg.paths.storagePersistingEnable && cfg.paths.storagePersistingIsExternalDrive)
            {
              description = "Periodic mount check for endoreg persisting storage";
              wantedBy = [ "timers.target" ];
              timerConfig = {
                OnBootSec = "1m";
                OnUnitActiveSec = "5m";
                Unit = "endoreg-mount-persisting-storage.service";
              };
            };
      };
    };
}
