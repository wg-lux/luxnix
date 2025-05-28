let
  # Primary NVMe (EFI + swap + Btrfs root)
  primaryNVME = "/dev/disk/by-id/nvme-KINGSTON_SFYRD4000G_50026B7686F7C454";

  # Additional NVMe disks
  dataNVME1   = "/dev/disk/by-id/nvme-KINGSTON_SFYRD4000G_50026B7686F7C8E05";
  dataNVME2   = "/dev/disk/by-id/nvme-KINGSTON_SFYRD4000G_50026B7686F7C8E35";

  # Four 6 TB HDD drives (LUKS + Btrfs RAID1)
  hdd0        = "/dev/disk/by-id/ata-ST6000NE000-2KR101_WSD9GTCG";
  hdd1        = "/dev/disk/by-id/ata-ST6000NE000-2KR101_WSD9GTZ0";
  hdd2        = "/dev/disk/by-id/ata-ST6000NE000-2KR101_WSD9J076";
  hdd3        = "/dev/disk/by-id/ata-ST6000NE000-2KR101_WSD9MWWY";

  # Swap size on the primary NVMe swap partition
  swapSize = "16G";
in
{
  disko.devices = {
    disk = {
      ########################################################################
      # PRIMARY NVMe
      ########################################################################
      primary = {
        device = primaryNVME;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            EFI = {
              label = "boot";
              name = "EFI";
              size = "512M";
              type = "EF00";  # EFI partition
              content = {
                type = "filesystem";
                format = "vfat";
                mountpoint = "/boot";
              };
            };

            swapPartition = {
              label = "swap";
              name = "swap";
              size = swapSize;
              type = "8200";  # Linux swap
              content = {
                type = "swap";
              };
            };

            rootEncrypted = {
              label = "root_luks";
              name = "root_luks";
              size = "1T"; # System partition around 1TB
              content = {
                type = "luks";
                name = "cryptroot"; # Name for /dev/mapper/cryptroot
                # Add keyFile or passwordFile options here if needed for unlocking
                # settings.keyFile = "/path/to/keyfile";
                content = {
                  type = "btrfs";
                  extraArgs = [
                    "-f"
                    "-L" "nixos"  # Btrfs volume label
                  ];
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

            dataOnPrimary = {
              label = "data2_primary";
              name = "data2_primary";
              size = "100%"; # Remaining space
              content = {
                type = "btrfs";
                extraArgs = [ "-f" "-L" "data2_primary" ];
                subvolumes = {
                  "main" = {
                    mountpoint = "/data2"; # Mounted as /data2
                    mountOptions = [ "subvol=main" "compress=zstd" "noatime" ];
                  };
                };
              };
            };
          };
        };
      };

      ########################################################################
      # TWO Additional NVMes for Data
      ########################################################################
      data_aux1_disk = { # Renamed from data1
        device = dataNVME1;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data = {
              label = "data_aux1"; # Changed label
              size = "100%";
              content = {
                type = "btrfs";
                extraArgs = [ "-f" "-L" "data_aux1" ]; # Changed Btrfs label
                subvolumes = {
                  "main" = {
                    mountpoint = "/data_aux1"; # Changed mountpoint
                    mountOptions = [ "subvol=main" "compress=zstd" "noatime" ];
                  };
                };
              };
            };
          };
        };
      };

      data_aux2_disk = { # Renamed from data2
        device = dataNVME2;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data = {
              label = "data_aux2"; # Changed label
              size = "100%";
              content = {
                type = "btrfs";
                extraArgs = [ "-f" "-L" "data_aux2" ]; # Changed Btrfs label
                subvolumes = {
                  "main" = {
                    mountpoint = "/data_aux2"; # Changed mountpoint
                    mountOptions = [ "subvol=main" "compress=zstd" "noatime" ];
                  };
                };
              };
            };
          };
        };
      };

      hdd0 = {
        device = hdd0;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data = { # Renamed from luks to data
              label = "btrfsHDD0"; # Changed label
              size = "100%";
              content = {
                type = "btrfs"; # Changed from luks
                # This partition will be part of the Btrfs array defined in hdd3
                # No subvolumes or mountpoints defined here directly.
                # extraArgs can be added if specific formatting options are needed for this individual device
                # before it's added to the array, but usually not necessary.
              };
            };
          };
        };
      };

      hdd1 = {
        device = hdd1;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data = { # Renamed from luks to data
              label = "btrfsHDD1"; # Changed label
              size = "100%";
              content = {
                type = "btrfs"; # Changed from luks
                # Part of Btrfs array in hdd3
              };
            };
          };
        };
      };

      hdd2 = {
        device = hdd2;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data = { # Renamed from luks to data
              label = "btrfsHDD2"; # Changed label
              size = "100%";
              content = {
                type = "btrfs"; # Changed from luks
                # Part of Btrfs array in hdd3
              };
            };
          };
        };
      };

      # The final disk includes the Btrfs multi-device array referencing hdd0..2
      hdd3 = {
        device = hdd3;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data = { # Renamed from luks to data
              label = "btrfsHDD3"; # Changed label
              size = "100%";
              content = {
                type = "btrfs"; # Changed from luks
                # This device itself is also part of the Btrfs array.
                # The array is defined here, incorporating the other HDDs.
                extraArgs = [
                  "-f"
                  "-L" "archive"
                  "-m" "raid1"  # metadata = RAID1
                  "-d" "raid1"  # data = RAID1
                  hdd0 # Use direct device variable
                  hdd1 # Use direct device variable
                  hdd2 # Use direct device variable
                  # hdd3 is implicitly included as the device where mkfs.btrfs is run
                ];
                subvolumes = {
                  "archive" = {
                    mountpoint = "/archive";
                    mountOptions = [
                      "subvol=archive"
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
  fileSystems."/persist".neededForBoot = true;
  fileSystems."/var/log".neededForBoot = true;

  # Disk and ZRAM swap settings
  zramSwap = {
    enable = true;
    memoryPercent = 20;
    priority = 100;
  };
}