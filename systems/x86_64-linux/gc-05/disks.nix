let
  # --- User-configurable Disk Identifiers ---
  systemDiskId = "/dev/disk/by-id/nvme-KINGSTON_OM8PGP4512Q-AI_50026B73829021B8";
  swapSize = "32G"; # Adjusted swap size
in
{
  disko.devices = {
    disk = {
      # Primary System Disk (only disk)
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
