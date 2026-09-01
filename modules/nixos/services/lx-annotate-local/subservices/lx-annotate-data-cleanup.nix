# Purpose: Define only the lx-annotate-data-cleanup.service unit and its matching triggers.
# Command: runLxAnnotateDataCleanup.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-data-cleanup = mkIf cfg.dataCleanup.enable {
    description = "Move duplicate anonymized lx-annotate payload into external archive storage";
    after = [
      "systemd-tmpfiles-setup.service"
    ]
    ++ encryptionServiceUnits;
    wants = encryptionServiceUnits;
    requires = encryptionServiceUnits;
    unitConfig = encryptedDataMountUnitConfig;
    serviceConfig = {
      Type = "oneshot";
      User = endoreg-service-user-name;
      Group = endoreg-service-group-name;
      WorkingDirectory = endoreg-service-user-home;
      ExecStart = "${dataCleanupScript}/bin/runLxAnnotateDataCleanup";
      ReadWritePaths = [
        endoreg-service-user-home
        envDataDir
        cfg.dataCleanup.archiveDir
        runtimeRootPath
        "/var/endoreg-service-user/lx-annotate"
        config.roles.endoreg-client.paths.storagePersistingMountPoint
      ];
    };
  };

  systemd.timers.lx-annotate-data-cleanup = mkIf cfg.dataCleanup.enable {
    description = "Periodic duplicate cleanup for anonymized lx-annotate legacy storage";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "15m";
      OnCalendar = cfg.dataCleanup.onCalendar;
      Unit = "lx-annotate-data-cleanup.service";
    };
  };
}
