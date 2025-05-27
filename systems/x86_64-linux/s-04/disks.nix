let
  # System disk (KOWIN 256GB SSD)
  systemDiskId = "/dev/disk/by-id/ata-KOWIN_KAE2000A256NS47_001B230300103264";

  # Placeholder for future external NVMe
  futureExternalNVMeId = "/dev/disk/by-id/placeholder-future-external-nvme";

  swapSize = "16G"; # Adjust as needed
in
{
  disko.devices = {
    disk = {
      system_disk = { # Renamed from nvme0n1 for clarity
        type = "disk";
        device = systemDiskId; # Updated to use stable ID
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
                mountOptions = [
                  "defaults"
                ];
              };
            };
            swap = { # Added swap partition
              label = "swap";
              name = "swap";
              size = swapSize;
              type = "8200"; # Linux swap
              content = {
                type = "swap";
              };
            };
            root_os = { # Replaces 'luks' partition, directly Btrfs
              label = "nixos_root";
              name = "root_os";
              size = "100%"; # Remaining space
              content = {
                type = "btrfs";
                extraArgs = [ "-L" "nixos" "-f" ];
                subvolumes = {
                  "/root" = {
                    mountpoint = "/";
                    mountOptions = [ "subvol=root" "compress=zstd" "noatime" ];
                  };
                  "/home" = {
                    mountpoint = "/home";
                    mountOptions = [ "subvol=home" "compress=zstd" "noatime" ];
                  };
                  "/nix" = {
                    mountpoint = "/nix";
                    mountOptions = [ "subvol=nix" "compress=zstd" "noatime" ];
                  };
                  "/persist" = {
                    mountpoint = "/persist";
                    mountOptions = [ "subvol=persist" "compress=zstd" "noatime" ];
                  };
                  "/log" = {
                    mountpoint = "/var/log";
                    mountOptions = [ "subvol=log" "compress=zstd" "noatime" ];
                  };
                  # Removed "/swap" subvolume and swapfile config
                };
              };
            };
          };
        };
      };

      # Placeholder for Future External NVMe
      future_external_nvme = {
        device = futureExternalNVMeId;
        type = "disk";
        # This part is commented out to prevent errors if the disk doesn't exist.
        # Uncomment and adjust when adding the disk.
        # content = {
        #   type = "gpt";
        #   partitions = {
        #     data = {
        #       label = "external_data";
        #       size = "100%";
        #       content = {
        #         type = "btrfs";
        #         label = "external_nvme_data";
        #         extraArgs = [ "-f" ];
        #         subvolumes = {
        #           "main" = {
        #             mountpoint = "/data_external";
        #             mountOptions = [ "subvol=main" "compress=zstd" "noatime" ];
        #           };
        #         };
        #       };
        #     };
        #   };
        # };
      };
    };
  };

  fileSystems."/persist".neededForBoot = true;
  fileSystems."/var/log".neededForBoot = true;

  # ZRAM Swap settings (added for consistency)
  zramSwap = {
    enable = true;
    memoryPercent = 20; # Use 20% of RAM for compressed swap
    priority = 100;     # Higher priority than disk-based swap partition
  };
}
