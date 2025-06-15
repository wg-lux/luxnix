let
  # --- User-configurable Disk Identifiers ---
  # System disk (approx. 500GB)
  systemDiskId = "/dev/disk/by-id/nvme-CT1000P1SSD8_2006E289C950";

  dataDisk1Id = "/dev/disk/by-id/nvme-Micron_3400_MTFDKBA1T0TFH_213330EC4FFF";



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
              name = "ESP"; # Nix attr name
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
              name = "swap"; # Nix attr name
              size = swapSize;
              type = "8200"; # Linux swap
              content = {
                type = "swap";
              };
            };
            root_os = {
              # Renamed from luks_root
              label = "nixos_root"; # GPT Label
              name = "root_os"; # Nix attr name
              size = "100%"; # Use remaining space
              content = {
                # Directly BTRFS, no LUKS
                type = "btrfs";
                extraArgs = [
                  "-f"
                  "-L"
                  "nixos"
                ];
                subvolumes = {
                  "root" = {
                    mountpoint = "/";
                    mountOptions = [
                      "subvol=root"
                      "compress=zstd"
                      "noatime"
                    ];
                  };
                  "home" = {
                    mountpoint = "/home";
                    mountOptions = [
                      "subvol=home"
                      "compress=zstd"
                      "noatime"
                    ];
                  };
                  "nix" = {
                    mountpoint = "/nix";
                    mountOptions = [
                      "subvol=nix"
                      "compress=zstd"
                      "noatime"
                    ];
                  };
                  "persist" = {
                    mountpoint = "/persist";
                    mountOptions = [
                      "subvol=persist"
                      "compress=zstd"
                      "noatime"
                    ];
                  };
                  "log" = {
                    mountpoint = "/var/log";
                    mountOptions = [
                      "subvol=log"
                      "compress=zstd"
                      "noatime"
                    ];
                  };
                };
              };
            };
          };
        };
      };

      # Data Disk 01 (single disk, no RAID)
      data_raid01_disk1 = {
        device = dataDisk1Id;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data_part = {
              label = "btrfs_data01_p1"; # GPT Label for the partition
              size = "100%";
              content = {
                type = "btrfs";
                extraArgs = [
                  "-f"
                  "-L"
                  "data_raid01"
                ];
                subvolumes = {
                  "storage" = {
                    mountpoint = "/data/raid01";
                    mountOptions = [
                      "subvol=storage"
                      "compress=zstd"
                      "noatime"
                    ];
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
  fileSystems = {
    "/persist".neededForBoot = true;
    "/var/log".neededForBoot = true;
    # If you create other critical mount points on the root filesystem, list them here.
  };

  # ZRAM Swap settings
  zramSwap = {
    enable = true;
    memoryPercent = 20; # Use 20% of RAM for compressed swap
    priority = 100; # Higher priority than disk-based swap partition
  };
}
