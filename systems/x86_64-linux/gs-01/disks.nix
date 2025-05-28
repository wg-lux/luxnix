let
  # --- User-configurable Disk Identifiers ---
  # System disk (approx. 500GB)
  systemDiskId = "/dev/disk/by-id/ata-CT500MX500SSD1_2247E689FA75";

  # First 3.5TB data disk
  dataDisk1Id = "/dev/disk/by-id/scsi-2000000000000000100a075223a1adb0f";

  # Second 3.5TB data disk
  dataDisk2Id = "/dev/disk/by-id/scsi-2000000000000000100a075223a1adb3d";

  # Placeholders for future disks
  futureDisk1Id = "/dev/disk/by-id/placeholder-future-disk-A";
  futureDisk2Id = "/dev/disk/by-id/placeholder-future-disk-B";

  swapSize = "64G"; # Adjusted swap size
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
              label = "boot"; # GPT Label
              name = "ESP";   # Nix attr name
              size = "512M";
              type = "EF00"; # EFI System Partition
              content = {
                type = "filesystem";
                format = "vfat";
                mountpoint = "/boot";
              };
            };
            swap = {
              label = "swap"; # GPT Label
              name = "swap";   # Nix attr name
              size = swapSize;
              type = "8200"; # Linux swap
              content = {
                type = "swap";
              };
            };
            root_os = { # Renamed from luks_root
              label = "nixos_root"; # GPT Label
              name = "root_os";    # Nix attr name
              size = "100%"; # Use remaining space
              content = { # Directly BTRFS, no LUKS
                type = "btrfs";
                extraArgs = [ "-f" "-L" "nixos_system" ];
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

      # Data RAID Array 01 (current 2x 3.5TB disks)
      data_raid01_disk1 = {
        device = dataDisk1Id;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data_part = { # Renamed from luks
              label = "btrfs_data01_p1"; # GPT Label for the partition
              size = "100%";
              # No content defined here; it's part of the BTRFS array defined on data_raid01_disk2
            };
          };
        };
      };

      data_raid01_disk2 = {
        device = dataDisk2Id;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data_part = { # Renamed from luks
              label = "btrfs_data01_p2"; # GPT Label for the partition
              size = "100%";
              content = { # Directly BTRFS, no LUKS
                type = "btrfs";
                extraArgs = [
                  "-f"
                  "-m" "raid1" # Metadata RAID1
                  "-d" "raid1" # Data RAID1
                  "-L" "data_raid01" # ADDED -L "data_raid01"
                  # Reference the partition on the other disk by its GPT label
                  "/dev/disk/by-partlabel/btrfs_data01_p1"
                  # The current partition (/dev/disk/by-partlabel/btrfs_data01_p2) is implicitly included
                ];
                subvolumes = {
                  "storage" = {
                    mountpoint = "/data/raid01";
                    mountOptions = [ "subvol=storage" "compress=zstd" "noatime" ];
                  };
                };
              };
            };
          };
        };
      };

      # Placeholder for Future Data RAID Array 02
      future_raid02_disk1 = {
        device = futureDisk1Id;
        type = "disk";
        # This part is commented out to prevent errors if the disk doesn't exist.
        # Uncomment and adjust when adding the disk.
        # content = {
        #   type = "gpt";
        #   partitions = {
        #     data_part = {
        #       label = "btrfs_future02_p1";
        #       size = "100%";
        #     };
        #   };
        # };
      };

      future_raid02_disk2 = {
        device = futureDisk2Id;
        type = "disk";
        # This part is commented out to prevent errors if the disk doesn't exist.
        # Uncomment and adjust when adding the disk.
        # content = {
        #   type = "gpt";
        #   partitions = {
        #     data_part = {
        #       label = "btrfs_future02_p2";
        #       size = "100%";
        #       content = {
        #         type = "btrfs";
        #         extraArgs = [
        #           "-f"
        #           "-m" "raid1"
        #           "-d" "raid1"
        #           "-L" "data_raid02_future" # ADDED -L (for consistency)
        #           "/dev/disk/by-partlabel/btrfs_future02_p1" # Assumes partition on futureDisk1Id
        #         ];
        #         subvolumes = {
        #           "storage" = {
        #             mountpoint = "/data/raid02_future";
        #             mountOptions = [ "subvol=storage" "compress=zstd" "noatime" ];
        #           };
        #         };
        #       };
        #     };
        #   };
        # };
      };
    };
  };

  # Mark subvolumes needed for boot
  fileSystems = {
    "/persist".neededForBoot = true;
    "/var/log".neededForBoot = true;
    # If you create other critical mount points on the root filesystem, list them here.
  };

  # ZRAM Swap settings
  zramSwap = {
    enable = true;
    memoryPercent = 20; # Use 20% of RAM for compressed swap
    priority = 100;     # Higher priority than disk-based swap partition
  };
}