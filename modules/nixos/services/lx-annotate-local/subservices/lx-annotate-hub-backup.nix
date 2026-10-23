# Purpose: Define only the lx-annotate-hub-backup.service unit and its matching triggers.
# Command: runLxAnnotateHubBackup.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-hub-backup = mkIf cfg.hub.backup.enable {
    description = "Create coupled PostgreSQL and protected lx-annotate hub runtime snapshots";
    after = [
      "lx-annotate.service"
      "postgresqlBackup.service"
    ]
    ++ encryptionServiceUnits;
    wants = [ "lx-annotate.service" ] ++ encryptionServiceUnits;
    requires = [ "postgresqlBackup.service" ] ++ encryptionServiceUnits;
    unitConfig = encryptedDataMountUnitConfig;
    serviceConfig = {
      Type = "oneshot";
      User = endoreg-service-user-name;
      Group = endoreg-service-group-name;
      WorkingDirectory = runtimeDataRootPath;
      ExecStart = "${runLocalHubBackupScript}/bin/runLxAnnotateHubBackup";
      LoadCredential = [
        "hub-postgresql.sql.gz:${config.services.postgresqlBackup.location}/all.sql.gz"
      ];
      ReadWritePaths = [
        envDataDir
        cfg.hub.backup.incomingDir
        cfg.hub.backup.snapshotDir
        cfg.hub.backup.manifestDir
        runtimeRootPath
      ];
    };
    path = [
      pkgs.coreutils
      pkgs.findutils
      pkgs.gzip
      pkgs.jq
      pkgs.rsync
    ];
  };

  systemd.timers.lx-annotate-hub-backup = mkIf cfg.hub.backup.enable {
    description = "Periodic protected snapshots for the lx-annotate hub node";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "10m";
      OnCalendar = cfg.hub.backup.onCalendar;
      Unit = "lx-annotate-hub-backup.service";
    };
  };
}
