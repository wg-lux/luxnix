{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.endoreg.sensitiveStorage;

  adminUser = config.user.admin.name;
  adminHome = config.users.users.${adminUser}.home or "/home/${adminUser}";
  sensitiveLogsDirectory = "${cfg.sensitiveDirectory}/logs";

  # Helper zur Erstellung der vollständigen Partitions-Konfiguration
  createPartitionConfig =
    label: group:
    let
      customCfg = cfg.partitionConfigurations."${label}" or { };
    in
    {
      inherit label group;
      inherit (cfg) user;
      keyFile = "${cfg.keyFileDirectory}/${label}.key";
      filemodeSecret = "0600";
      filemodeMountpoint = "0770";
      mountScriptName = "mount-${label}";
      umountScriptName = "umount-${label}";
      mountServiceName = "mount-${label}";
      umountServiceName = "umount-${label}";
      logScriptName = "log-${label}";
      logServiceName = "log-${label}";
      logTimerOnCalendar = "*:0/30"; # Alle 30 Minuten
      logDir = sensitiveLogsDirectory;
    }
    // customCfg;

  partitionList = [
    (createPartitionConfig "dropoff" "sensitive-storage-dropoff")
    (createPartitionConfig "processing" "sensitive-storage-processing")
    (createPartitionConfig "processed" "sensitive-storage-processed")
  ];

in
{
  options.endoreg.sensitiveStorage = {
    enable = mkBoolOpt false "Enable endoreg sensitive storage configuration";

    partitionConfigurations = mkOption {
      type = types.attrsOf (types.attrsOf types.str);
      description = ''
        Sensitive HDD configuration
      '';
      default = {
        dropoff = {
          label = "dropoff";
          uuid = "dummy";
          luks-uuid = "dummy";
          mountPoint = "dummy/c";
          filemodeSecret = "0700";
          filemodeMountpoint = "0750";
          mountScriptName = "mount-dropoff";
          umountScriptName = "umount-dropoff";
          mountServiceName = "mount-dropoff";
          umountServiceName = "umount-dropoff";
          keyFile = "dummy";
          user = "admin";
          group = "endoreg-service";
        };
        processing = {
          label = "processing";
          uuid = "dummy";
          luks-uuid = "dummy";
          mountPoint = "dummy/c";
          filemodeSecret = "0700";
          filemodeMountpoint = "0750";
          mountScriptName = "mount-processing";
          umountScriptName = "umount-processing"; # Korrigiert
          mountServiceName = "mount-processing";
          umountServiceName = "umount-processing"; # Korrigiert
          keyFile = "dummy2";
          user = "admin";
          group = "endoreg-service";
        };
        processed = {
          label = "processed";
          uuid = "dummy";
          luks-uuid = "dummy";
          mountPoint = "dummy/c";
          filemodeSecret = "0700";
          filemodeMountpoint = "0750";
          mountScriptName = "mount-processed";
          umountScriptName = "umount-processed"; # Korrigiert
          mountServiceName = "mount-processed";
          umountServiceName = "umount-processed"; # Korrigiert
          keyFile = "dummy3";
          user = "admin";
          group = "endoreg-service";
        };
      };
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
      default = "${adminHome}/.config/endoreg-sensitive-keyfiles";
      description = ''
        Directory where keyfiles are stored
      '';
    };

    sensitiveDirectory = mkOption {
      type = types.str;
      default = "/mnt/endoreg-sensitive-storage";
    };
  };

  config = mkIf cfg.enable (mkMerge [
    {
      users.groups = {
        "sensitive-storage-dropoff" = {
          gid = 3301;
          members = [
            adminUser
            cfg.user
          ];
        };
        "sensitive-storage-processing" = {
          gid = 3302;
          members = [
            adminUser
            cfg.user
          ];
        };
        "sensitive-storage-processed" = {
          gid = 3303;
          members = [
            adminUser
            cfg.user
          ];
        };
        "sensitive-storage-keyfiles" = {
          gid = 3304;
          members = [
            adminUser
            cfg.user
          ];
        };
      };

      systemd.tmpfiles.rules = [
        "d ${cfg.sensitiveDirectory} 0770 ${adminUser} endoreg-service -"
        "d ${sensitiveLogsDirectory} 0770 ${adminUser} endoreg-service -"
        "d ${cfg.keyFileDirectory} 0700 ${adminUser} endoreg-service -"
      ];

      security.polkit.extraConfig = ''
        polkit.addRule(function(action, subject) {
            var units = ["dropoff", "processing", "processed"];
            for (var i = 0; i < units.length; i++) {
                var u = units[i];
                var group = "sensitive-storage-" + u;
                if ((action.lookup("unit") == "mount-" + u + ".service" || 
                    action.lookup("unit") == "umount-" + u + ".service" || 
                    action.lookup("unit") == "log-" + u + ".service") &&
                    (subject.isInGroup(group) || subject.user == "${adminUser}") &&
                    (action.lookup("verb") == "start" || action.lookup("verb") == "stop" || action.lookup("verb") == "restart")) {
                    return polkit.Result.YES;
                }
            }
        });
      '';
    }

    # Dynamische Generierung aller Partitions-Mounts und Logger
    (mkMerge (
      map (
        partitionConfig:
        mkMerge [
          (import ./partition-mounting.nix {
            inherit config pkgs lib;
            partitionConfiguration = partitionConfig;
          })
          (import ./log-sensitive-partitions.nix {
            inherit config pkgs lib;
            partitionConfiguration = partitionConfig;
          })
        ]
      ) partitionList
    ))
  ]);
}
