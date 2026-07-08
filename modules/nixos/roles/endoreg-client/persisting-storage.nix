{ lib }:
{
  entrypoint =
    {
      cfg,
      config,
      pkgs,
      adminUserName,
      storagePersistingMountPoint,
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
              description = "Mount endoreg persisting storage via devenv";
              serviceConfig = {
                Type = "oneshot";
                User = "root";
                Environment = [
                  "STORAGE_PERSISTING_EXTERNAL_DRIVE=${
                    if cfg.paths.storagePersistingIsExternalDrive then "true" else "false"
                  }"
                  "STORAGE_PERSISTING_MOUNT_POINT=${toString storagePersistingMountPoint}"
                  "STORAGE_PERSISTING_HDD_ID=${
                    lib.attrByPath [ "secretspec" "secrets" "STORAGE_PERSISTING_HDD_ID" ] "" config
                  }"
                  "STORAGE_PERSISTING_HDD_PART=${
                    lib.attrByPath [ "secretspec" "secrets" "STORAGE_PERSISTING_HDD_PART" ] "part1" config
                  }"
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

                  # Check if already mounted
                  if mountpoint -q "$storage_persisting_mount_point"; then
                    echo "Persisting storage already mounted at $storage_persisting_mount_point"
                    exit 0

                  fi

                  # attempt to mount drive by ID; prefer first partition if present
                  DEV_BASE="/dev/disk/by-id/$storage_persisting_hdd_id"
                  DEV_PATH="$DEV_BASE-$storage_persisting_hdd_part"


                  echo "Mounting persisting storage drive $DEV_PATH to $storage_persisting_mount_point"
                  if [ ! -e "$DEV_PATH" ]; then
                    echo "WARNING: Device path $DEV_PATH does not exist; leaving persisting storage unmounted"
                    exit 0
                  fi

                  if ! mount "$DEV_PATH" "$storage_persisting_mount_point"; then
                    echo "WARNING: Failed to mount persisting storage drive $DEV_PATH; leaving it unmounted"
                    exit 0
                  fi
                  echo "Mounted persisting storage successfully" 

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
