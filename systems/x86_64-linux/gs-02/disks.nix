let
  # Primary NVMe (EFI + swap + Btrfs root)
  primaryNVME = "/dev/disk/by-id/nvme-KINGSTON_SFYRD4000G_50026B7686F7C454";

  # Additional NVMe disks
  dataNVME1   = "/dev/disk/by-id/nvme-KINGSTON_SFYRD4000G_50026B7686F7C8E0";
  dataNVME2   = "/dev/disk/by-id/nvme-KINGSTON_SFYRD4000G_50026B7686F7C8E3";

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
              size = "1T";
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
            dataOnPrimary = {
              label = "data2_primary";
              name = "data_primary_nvme_part";
              size = "100%";
              content = {
                type = "btrfs";
                extraArgs = [ "-f" "-L" "data2_primary" ];
                subvolumes = {
                  "main" = {
                    mountpoint = "/data2";
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
              label = "data_aux1"; 
              name = "data_aux1_nvme_part"; 
              size = "100%";
              content = {
                type = "btrfs";
                extraArgs = [ "-f" "-L" "data_aux1" ]; 
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
              name = "data_aux2_nvme_part"; # ADDED GPT partition name
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
              name = "btrfsHDD0_part"; # GPT partition name
              label = "archive_hdd0"; # ADDED GPT partition label
              size = "100%";
              # No 'content' block here, this partition is a member of the Btrfs array defined on hdd3
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
              name = "btrfsHDD1_part"; # GPT partition name
              label = "archive_hdd1"; # ADDED GPT partition label
              size = "100%";
              # No 'content' block here, this partition is a member of the Btrfs array defined on hdd3
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
              name = "btrfsHDD2_part"; # GPT partition name
              label = "archive_hdd2"; # ADDED GPT partition label
              size = "100%";
              # No 'content' block here, this partition is a member of the Btrfs array defined on hdd3
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
              name = "btrfsHDD3_part"; # GPT partition name
              label = "archive_hdd3"; # ADDED GPT partition label
              size = "100%";
              content = {
                type = "btrfs";
                extraArgs = [
                  "-f"
                  "-L" "archive"
                  "-m" "raid1c3"  # metadata = RAID1c3 for 4 drives
                  "-d" "raid1"    # data = RAID1
                  "/dev/disk/by-partlabel/archive_hdd0"
                  "/dev/disk/by-partlabel/archive_hdd1"
                  "/dev/disk/by-partlabel/archive_hdd2"
                  # The partition on hdd3 (/dev/disk/by-partname/btrfsHDD3_part) is implicitly the first device
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