# Purpose: Define only the lx-annotate-master-key-check.service unit.
# Command: runLocalMasterKeyCheck.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-master-key-check = {
    description = "Validate lx-annotate application master key against encrypted storage";
    wantedBy = [ "multi-user.target" ];
    before = [ "lx-annotate.service" ];
    after = [
      "systemd-tmpfiles-setup.service"
      "lx-annotate-runtime-env.service"
      "lx-annotate-load-base-data.service"
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
    ]
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    restartTriggers = [ effectiveRuntimePackage ];
    unitConfig = encryptedDataMountUnitConfig;
    environment = commonExtraEnv;
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      User = endoreg-service-user-name;
      Group = endoreg-service-group-name;
      SupplementaryGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];
      WorkingDirectory = runtimeDataRootPath;
      ExecStart = "${runLocalMasterKeyCheckScript}/bin/runLocalMasterKeyCheck";
      EnvironmentFile = envSystemdFilePath;
      LogNamespace = lxAnnotateJournalNamespace;
      TimeoutStartSec = "10min";
      ProtectSystem = "full";
      PrivateTmp = true;
      NoNewPrivileges = true;
      ReadWritePaths = appReadWritePaths;
    };
  };
}
