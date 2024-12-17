{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.endoreg.sensitive-storage;

  sensitiveDataDirectory = "${cfg.sensitiveDirectory}/data";
  sensitiveLogsDirectory = "${cfg.sensitiveDirectory}/logs";
  # get mountpoint directory helper function (expects sensitiveDataDirectory)
  # and returns "${sensitiveDataDirectory}/${label}"

in {
  options.endoreg.sensitive-storage = {
    enable = mkBoolOpt false "Enable endoreg sensitive storage configuration";
  
    partitionConfigurations = mkOption {
      type = types.attrsOf (types.attrsOf types.str);
      description = ''
        Sensitive HDD configuration
      '';
    };

    user = mkOption {
      type = types.str;
      default = "endoreg-service-user";
      description = ''
        User that will be used to access the sensitive storage
      '';
    };

    keyFileDirectory = mkOption {
      type = types.str;
      default = "/home/${config.user.admin.name}/.config/endoreg-sensitive-keyfiles";
      description = ''
        Directory where keyfiles are stored
      '';
    };

    sensitiveDirectory = mkOption {
      type = types.str;
      default = "/mnt/endoreg-sensitive-storage";
    };
  };

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
        filemodeMountpoint = "0770";
        mountScriptName = "mount-${label}";
        umountScriptName = "umount-${label}";
        mountServiceName = "mount-${label}";
        umountServiceName = "umount-${label}";
        logScriptName = "log-${label}";
        logServiceName = "log-${label}";
        logTimerOnCalendar = "*:0/30"; # Every 30 minutes
        logDir = sensitiveLogsDirectory;
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
      "d ${cfg.sensitiveDirectory} 0770 admin endoreg-service -"
      "d ${cfg.keyFileDirectory} 0700 admin endoreg-service -"
    ];

    security.polkit.extraConfig = ''
      polkit.addRule(function(action, subject) {
          // Allow users in group "sensitive-storage-dropoff" or "admin" to manage mount-dropoff and umount-dropoff services
          if ((action.lookup("unit") == "mount-dropoff.service" || 
              action.lookup("unit") == "umount-dropoff.service" || 
              action.lookup("unit") == "log-dropoff.service") &&
              (subject.isInGroup("sensitive-storage-dropoff") || subject.user == "admin") &&
              (action.lookup("verb") == "start" || action.lookup("verb") == "stop" || action.lookup("verb") == "restart")) {
              return polkit.Result.YES;
          }

          // Allow users in group "sensitive-storage-processing" or "admin" to manage mount-processing and umount-processing services
          if ((action.lookup("unit") == "mount-processing.service" || 
              action.lookup("unit") == "umount-processing.service" || 
              action.lookup("unit") == "log-processing.service") &&
              (subject.isInGroup("sensitive-storage-processing") || subject.user == "admin") &&
              (action.lookup("verb") == "start" || action.lookup("verb") == "stop" || action.lookup("verb") == "restart")) {
              return polkit.Result.YES;
          }

          // Allow users in group "sensitive-storage-processed" or "admin" to manage mount-processed and umount-processed services
          if ((action.lookup("unit") == "mount-processed.service" || 
              action.lookup("unit") == "umount-processed.service" || 
              action.lookup("unit") == "log-processed.service") &&
              (subject.isInGroup("sensitive-storage-processed") || subject.user == "admin") &&
              (action.lookup("verb") == "start" || action.lookup("verb") == "stop" || action.lookup("verb") == "restart")) {
              return polkit.Result.YES;
          }
      });
    '';



  };
}

