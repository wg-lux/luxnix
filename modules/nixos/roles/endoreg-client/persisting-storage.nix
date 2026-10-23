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
                TimeoutStartSec = "30s";
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

                  log_storage_event() {
                    jq -cn --arg state "$1" --arg mount_point "$storage_persisting_mount_point" \
                      --argjson devices "$detected_devices" \
                      '{event: "endoreg.external_storage", state: $state, mount_point: $mount_point, devices: $devices}'
                  }

                  detected_devices='[]'
                  # if STORAGE_PERSISTING_EXTERNAL_DRIVE is not true, exit
                  if [ "$storage_persisting_external_drive" != "true" ]; then
                    log_storage_event disabled
                    exit 0

                  fi

                  if [ -z "$storage_persisting_mount_point" ]; then
                    log_storage_event invalid_mount_point >&2
                    exit 1
                  fi

                  # USB hard disks commonly report RM=false. HOTPLUG also
                  # covers removable transports other than USB. Discovery is
                  # advisory: never enroll or mount an arbitrary detected disk.
                  detected_devices=$(lsblk --json --paths --output NAME,TYPE,TRAN,RM,HOTPLUG | jq -ce '
                    .blockdevices | if type != "array" then error("invalid block-device inventory") else . end |
                    [.. | objects | select(.type == "disk" and
                      (.tran == "usb" or .rm == true or .rm == 1 or .hotplug == true or .hotplug == 1)) |
                      {name, transport: .tran, removable: .rm, hotplug: .hotplug}] | unique_by(.name)')

                  if [ -z "$storage_persisting_hdd_id" ]; then
                    if mountpoint -q "$storage_persisting_mount_point"; then
                      log_storage_event unverified_existing_mount >&2
                      exit 1
                    fi
                    if [ "$detected_devices" = '[]' ]; then
                      log_storage_event absent
                    else
                      log_storage_event enrollment_required
                    fi
                    exit 0
                  fi

                  # Always verify the configured device, including an existing
                  # mount: a USB reconnect can leave a stale device number mounted.
                  DEV_BASE="/dev/disk/by-id/$storage_persisting_hdd_id"
                  DEV_PATH="$DEV_BASE-$storage_persisting_hdd_part"
                  if [ ! -b "$DEV_PATH" ]; then
                    if mountpoint -q "$storage_persisting_mount_point"; then
                      log_storage_event lost >&2
                      exit 1
                    fi
                    log_storage_event configured_device_absent
                    exit 0
                  fi
                  expected_device_number=$(lsblk -dnro MAJ:MIN "$DEV_PATH")
                  if [[ ! "$expected_device_number" =~ ^[0-9]+:[0-9]+$ ]]; then
                    log_storage_event invalid_device_identity >&2
                    exit 1
                  fi
                  if ! mountpoint -q "$storage_persisting_mount_point"; then
                    log_storage_event mounting
                    if mount "$DEV_PATH" "$storage_persisting_mount_point"; then
                      :
                    else
                      mount_status=$?
                      log_storage_event mount_failed >&2
                      exit "$mount_status"
                    fi
                  fi
                  mounted_device_number=$(findmnt -n -o MAJ:MIN --mountpoint "$storage_persisting_mount_point")
                  if [ ! -b "$DEV_PATH" ] || \
                     [ "$(lsblk -dnro MAJ:MIN "$DEV_PATH")" != "$expected_device_number" ] || \
                     [ "$mounted_device_number" != "$expected_device_number" ]; then
                    log_storage_event lost >&2
                    exit 1
                  fi
                  log_storage_event verified
                '';
              };
              path = [
                pkgs.coreutils
                pkgs.util-linux
                pkgs.jq
              ];
            };

        systemd.timers.endoreg-mount-persisting-storage =
          lib.mkIf (cfg.paths.storagePersistingEnable && cfg.paths.storagePersistingIsExternalDrive)
            {
              description = "Periodic mount check for endoreg persisting storage";
              wantedBy = [ "timers.target" ];
              timerConfig = {
                OnBootSec = "1m";
                OnUnitInactiveSec = "30s";
                AccuracySec = "1s";
                Unit = "endoreg-mount-persisting-storage.service";
              };
            };
      };
    };
}
