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
    ]
    ++ dataRecoveryServiceUnits
    ++ localRedisServiceUnits
    ++ localPostgresServiceUnits
    ++ localPostgresSetupUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    requires = [
      "lx-annotate-runtime-env.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ]
    ++ dataRecoveryServiceUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    after = [
      "lx-annotate-runtime-env.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
      "endoreg-django-setup.service"
      "systemd-tmpfiles-setup.service"
    ]
    ++ dataRecoveryServiceUnits
    ++ localRedisServiceUnits
    ++ localPostgresServiceUnits
    ++ localPostgresSetupUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    unitConfig = encryptedDataMountUnitConfig // {
      # Keep retrying transient process failures without a permanent rate-limit latch.
      StartLimitIntervalSec = 0;
    };
    serviceConfig = {
      TimeoutStartSec = "5min";
      Restart = mkForce "always";
      RestartSec = mkForce 30;
      # Recycle the whole web cgroup if an OOM kill leaves the master alive.
      OOMPolicy = "stop";
      LogNamespace = lxAnnotateJournalNamespace;
      MemoryHigh = cfg.runtime.limits.memoryHigh;
      MemoryMax = cfg.runtime.limits.memoryMax;
      CPUQuota = cfg.runtime.limits.cpuQuota;
      Nice = 0;
      IOSchedulingClass = "best-effort";
      IOSchedulingPriority = 4;
      OOMScoreAdjust = 0;
      ProtectSystem = "full";
      PrivateTmp = true;
      NoNewPrivileges = true;
      SupplementaryGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];
      ReadWritePaths = appReadWritePaths;
    };
  };
}
