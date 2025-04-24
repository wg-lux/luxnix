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

            root = {
              label = "root";
              name = "root";
              size = "100%";
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
        };
      };

      ########################################################################
      # TWO Additional NVMes for Data
      ########################################################################
      data1 = {
        device = dataNVME1;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data = {
              label = "data1";
              size = "100%";
              content = {
                type = "btrfs";
                extraArgs = [ "-f" "-L" "data1" ];
                subvolumes = {
                  "main" = {
                    mountpoint = "/data1";
                    mountOptions = [ "subvol=main" "compress=zstd" "noatime" ];
                  };
                };
              };
            };
          };
        };
      };

      data2 = {
        device = dataNVME2;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            data = {
              label = "data2";
              size = "100%";
              content = {
                type = "btrfs";
                extraArgs = [ "-f" "-L" "data2" ];
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
      # Four 6 TB HDDs with LUKS Encryption + Btrfs RAID1
      ########################################################################
      hdd0 = {
        device = hdd0;
        type = "disk";
        content = {
          type = "gpt";
          partitions = {
            luks = {
              label = "luksHDD0";
              size = "100%";
              content = {
                type = "luks";
                name = "cryptHDD0";
                extraOpenArgs = [
                  "--allow-discards"
                  "--perf-no_read_workqueue"
                  "--perf-no_write_workqueue"
                ];
                settings = {
                  # For passphrase-based, remove or adjust
                  # crypttabExtraOpts = [ "fido2-device=auto" "token-timeout=10" ];
                };
                # Btrfs array is defined in hdd3's config
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
            luks = {
              label = "luksHDD1";
              size = "100%";
              content = {
                type = "luks";
                name = "cryptHDD1";
                extraOpenArgs = [
                  "--allow-discards"
                  "--perf-no_read_workqueue"
                  "--perf-no_write_workqueue"
                ];
                settings = {
                  # crypttabExtraOpts = [ "fido2-device=auto" "token-timeout=10" ];
                };
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
            luks = {
              label = "luksHDD2";
              size = "100%";
              content = {
                type = "luks";
                name = "cryptHDD2";
                extraOpenArgs = [
                  "--allow-discards"
                  "--perf-no_read_workqueue"
                  "--perf-no_write_workqueue"
                ];
                settings = {
                  # crypttabExtraOpts = [ "fido2-device=auto" "token-timeout=10" ];
                };
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
            luks = {
              label = "luksHDD3";
              size = "100%";
              content = {
                type = "luks";
                name = "cryptHDD3";
                extraOpenArgs = [
                  "--allow-discards"
                  "--perf-no_read_workqueue"
                  "--perf-no_write_workqueue"
                ];
                settings = {
                  # crypttabExtraOpts = [ "fido2-device=auto" "token-timeout=10" ];
                };
                content = {
                  type = "btrfs";
                  extraArgs = [
                    "-f"
                    "-L" "archive"
                    "-m" "raid1"  # metadata = RAID1
                    "-d" "raid1"  # data = RAID1
                    "/dev/mapper/cryptHDD0"
                    "/dev/mapper/cryptHDD1"
                    "/dev/mapper/cryptHDD2"
                    # cryptHDD3 is implicit
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