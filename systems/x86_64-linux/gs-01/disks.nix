let
  # --- User-configurable Disk Identifiers ---
  # System disk (approx. 500GB)
  systemDiskId = "/dev/disk/by-id/ata-CT500MX500SSD1_2247E689FA75";

  # First 3.5TB data disk
  dataDisk1Id = "/dev/disk/by-id/scsi-2000000000000000100a075223a1adb0f";

  # Second 3.5TB data disk
  dataDisk2Id = "/dev/disk/by-id/scsi-2000000000000000100a075223a1adb3d";

  swapSize = "64G";
in
{
  disko.devices = {
    disk = {
      # Primary System Disk
      system_disk = {
        device = systemDiskId;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            ESP = {
              label = "boot";
              name = "ESP";
              size = "512M";
              type = "EF00";
              content = {
                type = "filesystem";
                format = "vfat";
                mountpoint = "/boot";
              };
            };
            swap = {
              label = "swap";
              name = "swap";
              size = swapSize;
              type = "8200";
              content = {
                type = "swap";
              };
            };
            root_os = {
              label = "nixos_root";
              name = "root_os";
              size = "100%";
              content = {
                type = "btrfs";
                extraArgs = [ "-f" "-L" "nixos" ];
                subvolumes = {
                  "root" = {
                    mountpoint = "/";
                    mountOptions = [ "subvol=root" "compress=zstd" "noatime" ];
                  };
                  "home" = {
                    mountpoint = "/home";
                    mountOptions = [ "subvol=home" "compress=zstd" "noatime" ];
                  };
                  "nix" = {
                    mountpoint = "/nix";
                    mountOptions = [ "subvol=nix" "compress=zstd" "noatime" ];
                  };
                  "persist" = {
                    mountpoint = "/persist";
                    mountOptions = [ "subvol=persist" "compress=zstd" "noatime" ];
                  };
                  "log" = {
                    mountpoint = "/var/log";
                    mountOptions = [ "subvol=log" "compress=zstd" "noatime" ];
                  };
                };
              };
            };
          };
        };
      };

      # Data Disk 1 (no content, just partition for Btrfs array)
      data_disk1 = {
        device = dataDisk1Id;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data = {
              label = "archive_data1";
              name = "btrfsDATA1_part";
              size = "100%";
              # No content block; member of Btrfs array defined on data_disk2
            };
          };
        };
      };

      # Data Disk 2 (defines the Btrfs array)
      data_disk2 = {
        device = dataDisk2Id;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data = {
              label = "archive_data2";
              name = "btrfsDATA2_part";
              size = "100%";
              content = {
                type = "btrfs";
                extraArgs = [
                  "-f"
                  "-L" "archive"
                  "-m" "raid1"
                  "-d" "raid1"
                  "/dev/disk/by-partlabel/archive_data1"
                  # The partition on data_disk2 (/dev/disk/by-partlabel/archive_data2) is implicitly included
                ];
                subvolumes = {
                  "storage" = {
                    mountpoint = "/archive";
                    mountOptions = [ "subvol=storage" "compress=zstd" "noatime" ];
                  };
                };
              };
            };
          };
        };
      };
    };
  };

  # Mark subvolumes needed for boot
  fileSystems."/persist".neededForBoot = true;
  fileSystems."/var/log".neededForBoot = true;

  # ZRAM Swap settings
  zramSwap = {
    enable = true;
    memoryPercent = 20;
    priority = 100;
  };
}