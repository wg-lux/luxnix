# Purpose: Define only the lx-annotate.service unit.
# Command: Upstream-owned by services.lx-annotate; this module adds ordering and resource controls.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate = {
    aliases = [ "lx-annotate-boot.service" ];
    wants = [
      "nginx.service"
      "lx-annotate-runtime-env.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-preflight.service"
    ]
    ++ dataRecoveryServiceUnits
    ++ hlsBackfillServiceUnits
    ++ localRedisServiceUnits
    ++ localPostgresServiceUnits
    ++ localPostgresSetupUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    requires = [
      "lx-annotate-runtime-env.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
      "lx-annotate-preflight.service"
    ]
    ++ dataRecoveryServiceUnits
    ++ hlsBackfillServiceUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    after = [
      "lx-annotate-runtime-env.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
      "lx-annotate-preflight.service"
      "endoreg-django-setup.service"
      "systemd-tmpfiles-setup.service"
    ]
    ++ dataRecoveryServiceUnits
    ++ hlsBackfillServiceUnits
    ++ localRedisServiceUnits
    ++ localPostgresServiceUnits
    ++ localPostgresSetupUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    unitConfig = encryptedDataMountUnitConfig;
    serviceConfig = {
      TimeoutStartSec = "5min";
      Restart = "on-failure";
      RestartSec = mkDefault 5;
      LogNamespace = lxAnnotateJournalNamespace;
      MemoryHigh = cfg.runtime.limits.memoryHigh;
      MemoryMax = cfg.runtime.limits.memoryMax;
      CPUQuota = cfg.runtime.limits.cpuQuota;
      Nice = 10;
      IOSchedulingClass = "best-effort";
      IOSchedulingPriority = 6;
      OOMScoreAdjust = 250;
      ProtectSystem = "full";
      PrivateTmp = true;
      NoNewPrivileges = true;
      SupplementaryGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];
      ReadWritePaths = appReadWritePaths;
    };
  };
}
