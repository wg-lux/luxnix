{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.endoreg.sensitive-storage;

  # get mountpoint directory helper function (expects sensitiveDataDirectory)
  # and returns "${sensitiveDataDirectory}/${label}"

in {
  options.endoreg.sensitive-storage = {
    enable = mkEnableOption "Enable endoreg sensitive storage configuration";
  
    partitionConfigurations = mkOption {
      type = types.attrsOf types.string;
      description = ''
        Sensitive HDD configuration
      '';
    };

    user = mkOption {
      type = types.string;
      default = "endoreg-service-user";
      description = ''
        User that will be used to access the sensitive storage
      '';
    };

    keyFileDirectory = mkOption {
      type = types.string;
      default = "/home/${config.user.admin.name}/.config/endoreg-sensitive-keyfiles";
      description = ''
        Directory where keyfiles are stored
      '';
    };

    sensitiveDataDirectory = mkOption {
      type = types.string;
      default = "/mnt/endoreg-sensitive-storage";
    };
  };



  config = mkIf cfg.enable {

    users.groups = {
      "sensitive-storage-dropoff" = {
        gid = 3301;
        members = [ #TODO harden for production 
          "admin"
          "${cfg.user}"
        ];
      };
      "sensitive-storage-processing" = {
        gid = 3302;
        members = [ #TODO harden for production 
          "admin"
          "${cfg.user}"
        ];
      };
      "sensitive-storage-processed" = {
        gid = 3303;
        members = [ #TODO harden for production 
          "admin"
          "${cfg.user}"
        ];
      };
      "sensitive-storage-keyfiles" = {
        gid = 3304;
        members = [ #TODO harden for production 
          "admin"
          "${cfg.user}"
        ];
      };
    };

    systemd.tmpfiles.rules = [
      # USB Encrypter
      "d ${cfg.sensitiveDataDirectory} 0770 admin endoreg-service -"
      "d ${cfg.keyFileDirectory} 0700 admin endoreg-service -"
    ];

    imports = 
    let
      # create helper function wich accepts "label" and returns a configuration dict
      createPartitionConfig = { label, group }:
        {
          label = label;
          user = cfg.user;
          group = group;
          keyFile = "${cfg.keyFileDirectory}/${label}.key";
          filemodeSecret = "0600";
          filemodeMountpoint = "0700";
          mountScriptName = "mount-${label}";
          umountScriptName = "umount-${label}";
          mountServiceName = "mount-${label}";
          umountServiceName = "umount-${label}";
          logScriptName = "log-${label}";
          logServiceName = "log-${label}";
          logTimerOnCalendar = "*:0/30"; # Every 30 minutes
          logDir = "/var/log/endoreg-sensitive-storage";
        } // cfg.partitionConfigurations."${label}";

        dropoffConfig = createPartitionConfig { label = "dropoff"; group = "sensitive-storage-dropoff"; };
        processingConfig = createPartitionConfig { label = "processing"; group = "sensitive-storage-processing"; };
        processedConfig = createPartitionConfig { label = "processed"; group = "sensitive-storage-processed"; };

    in [
        ##### Mounting 
        ( import ./partition-mounting.nix 
          {
            inherit config pkgs lib;
            partitionConfiguration = dropoffConfig;
            })
        ( import ./partition-mounting.nix {
          inherit config pkgs lib;
          partitionConfiguration = processingConfig;
        })
        ( import ./partition-mounting.nix {
          inherit config pkgs lib;
          partitionConfiguration = processedConfig;
        })

        #### Loggers
        ( import ./log-sensitive-partitions.nix {
          inherit config pkgs lib;
          partitionConfiguration = dropoffConfig;
         })
        ( import ./log-sensitive-partitions.nix {
          inherit config pkgs lib;
          partitionConfiguration = processingConfig;
        })
        ( import ./log-sensitive-partitions.nix {
          inherit config pkgs lib;
          partitionConfiguration = processedConfig;
        })
    ];


  };
}

