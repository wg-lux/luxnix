# Purpose: Define only the lx-annotate-emergency-storage-relief.service unit and its matching triggers.
# Command: runLxAnnotateEmergencyStorageRelief.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-emergency-storage-relief = mkIf cfg.storageRelief.enable {
    description = "Emergency lx-annotate storage relief to verified external archive";
    after = [
      "systemd-tmpfiles-setup.service"
      "lx-annotate-runtime-env.service"
    ]
    ++ localPostgresServiceUnits
    ++ localPostgresSetupUnits

    ++ encryptionServiceUnits;
    wants = [
      "lx-annotate-runtime-env.service"
    ]

    ++ encryptionServiceUnits;
    requires = [
      "lx-annotate-runtime-env.service"
    ]

    ++ encryptionServiceUnits;
    unitConfig = {
      RequiresMountsFor = [
        envDataDir
      ]
      ++ lib.optionals cfg.storageRelief.requireExternalMount [
        cfg.storageRelief.externalMountPoint
      ];
    };
    environment = commonExtraEnv;
    serviceConfig = {
      Type = "oneshot";
      User = endoreg-service-user-name;
      Group = endoreg-service-group-name;
      WorkingDirectory = runtimeDataRootPath;
      ExecStart = "${emergencyStorageReliefScript}/bin/runLxAnnotateEmergencyStorageRelief";
      EnvironmentFile = envSystemdFilePath;
      TimeoutStartSec = "infinity";
      Nice = 19;
      IOSchedulingClass = "idle";
      OOMScoreAdjust = 900;
      ProtectSystem = "full";
      PrivateTmp = true;
      NoNewPrivileges = true;
      ReadWritePaths = [
        endoreg-service-user-home
        envDataDir
        envConfDir
        runtimeRootPath
        cfg.storageRelief.externalMountPoint
      ];
    };
    path = [
      pkgs.coreutils
      pkgs.findutils
      pkgs.util-linux
    ];
  };

  systemd.timers.lx-annotate-emergency-storage-relief =
    mkIf (cfg.storageRelief.enable && cfg.storageRelief.timer.enable)
      {
        description = "Periodic emergency lx-annotate storage relief";
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "20m";
          OnCalendar = cfg.storageRelief.timer.onCalendar;
          Unit = "lx-annotate-emergency-storage-relief.service";
        };
      };
}
