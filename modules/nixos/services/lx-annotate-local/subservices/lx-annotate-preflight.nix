# Purpose: Define only the lx-annotate-preflight.service unit.
# Command: lx-annotate-manage check and verify_encrypted_storage, then verifies the static manifest.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-preflight = {
    description = "Gate LX-Annotate web and workers on production runtime readiness";
    before = [ "lx-annotate.service" ] ++ alwaysWorkerServiceUnits;
    after = [
      "lx-annotate-runtime-env.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ]
    ++ dataRecoveryServiceUnits
    ++ hlsBackfillServiceUnits
    ++ hubNodeProvisioningServiceUnits
    ++ localPostgresServiceUnits
    ++ localPostgresSetupUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    wants = [
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ]
    ++ dataRecoveryServiceUnits
    ++ hlsBackfillServiceUnits
    ++ hubNodeProvisioningServiceUnits
    ++ localPostgresServiceUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    requires = [
      "lx-annotate-runtime-env.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ]
    ++ dataRecoveryServiceUnits
    ++ hlsBackfillServiceUnits
    ++ hubNodeProvisioningServiceUnits
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
      EnvironmentFile = envSystemdFilePath;
      LogNamespace = lxAnnotateJournalNamespace;
      ExecStart = pkgs.writeShellScript "lx-annotate-preflight" ''
        set -euo pipefail
        ${effectiveRuntimePackage}/bin/lx-annotate-manage check --fail-level CRITICAL
        ${effectiveRuntimePackage}/bin/lx-annotate-manage verify_encrypted_storage
        test -s ${lib.escapeShellArg "${packageStaticRoot}/.vite/manifest.json"}
      '';
      TimeoutStartSec = "10min";
      ProtectSystem = "full";
      PrivateTmp = true;
      NoNewPrivileges = true;
      ReadWritePaths = appReadWritePaths;
    };
  };
}
