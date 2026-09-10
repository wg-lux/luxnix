# Purpose: Define only the lx-annotate-video-streamable-migration.service unit.
# Command: lx-annotate-migrate-video-streamable-storage.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-video-streamable-migration = mkIf cfg.streamableMigration.enable {
    description = "Backfill LX-Annotate streamable video artifacts";
    wantedBy = [ ];
    after = [
      "systemd-tmpfiles-setup.service"
      "lx-annotate-runtime-env.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ]
    ++ localPostgresServiceUnits
    ++ localPostgresSetupUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    wants = [
      "lx-annotate-load-base-data.service"
    ]
    ++ localPostgresServiceUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    requires = [
      "lx-annotate-runtime-env.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ]
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    restartTriggers = [ effectiveRuntimePackage ];
    unitConfig = encryptedDataMountUnitConfig;
    environment = commonExtraEnv;
    serviceConfig = {
      Type = "oneshot";
      User = endoreg-service-user-name;
      Group = endoreg-service-group-name;
      SupplementaryGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];
      WorkingDirectory = runtimeDataRootPath;
      ExecStart = lib.escapeShellArgs [
        "${lxAnnotateMigrateVideoStreamableStorageScript}/bin/lx-annotate-migrate-video-streamable-storage"
      ];
      EnvironmentFile = envSystemdFilePath;
      TimeoutStartSec = "infinity";
      Nice = 15;
      IOSchedulingClass = "best-effort";
      IOSchedulingPriority = 6;
      ProtectSystem = "full";
      PrivateTmp = true;
      NoNewPrivileges = true;
      ReadWritePaths = appReadWritePaths;
    };
  };
}
