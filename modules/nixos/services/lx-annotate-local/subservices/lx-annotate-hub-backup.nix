# Purpose: Pause writers for a fresh PostgreSQL dump and protected media capture.
# Command: systemctl start lx-annotate-hub-backup.service
{ ctx }:
with ctx;
{
  systemd = {
    # systemd.packages merges drop-ins into the generated system unit directory.
    packages = lib.optional cfg.hub.backup.enable hubBackupStartBarrier;
    services.lx-annotate-hub-backup = mkIf cfg.hub.backup.enable {
      description = "Capture a consistent PostgreSQL and protected hub runtime restore point";
      after = [ "postgresql.service" ];
      requires = [ "postgresql.service" ];
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "oneshot";
        User = "root";
        Group = endoreg-service-group-name;
        RuntimeDirectory = "luxnix-hub-backup";
        RuntimeDirectoryMode = "0710";
        RuntimeDirectoryPreserve = "yes";
        TimeoutStartSec = "24h";
        TimeoutStopSec = "10min";
        WorkingDirectory = runtimeDataRootPath;
        ExecStart = "${hubBackupCoordinator}/bin/luxnix-hub-backup capture";
        ExecStopPost = "${hubBackupCoordinator}/bin/luxnix-hub-backup recover";
        LimitCORE = 0;
        UMask = "0077";
      };
    };
    timers.lx-annotate-hub-backup = mkIf cfg.hub.backup.enable {
      description = "Periodic consistent protected hub snapshots";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "10m";
        OnCalendar = cfg.hub.backup.onCalendar;
        Unit = "lx-annotate-hub-backup.service";
      };
    };
  };
}
