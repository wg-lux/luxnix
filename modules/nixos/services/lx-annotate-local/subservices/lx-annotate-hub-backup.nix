# One writer pause covers a fresh PostgreSQL dump and protected media capture.
{ ctx }:
with ctx;
{
  # systemd.packages merges drop-ins into the generated system unit directory.
  systemd = {
    packages = lib.optional cfg.hub.backup.enable hubBackupStartBarrier;
    services = mkIf cfg.hub.backup.enable (
      lib.mkMerge [
        {
          lx-annotate-hub-backup = {
            description = "Capture a consistent PostgreSQL and protected hub runtime restore point";
            after = [ "postgresql.service" ] ++ encryptionServiceUnits;
            requires = [ "postgresql.service" ] ++ encryptionServiceUnits;
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
        }
      ]
    );

    timers = mkIf cfg.hub.backup.enable (
      lib.mkMerge [
        {
          lx-annotate-hub-backup = {
            description = "Periodic consistent protected hub snapshots";
            wantedBy = [ "timers.target" ];
            timerConfig = {
              OnBootSec = "10m";
              OnCalendar = cfg.hub.backup.onCalendar;
              Unit = "lx-annotate-hub-backup.service";
            };
          };
        }
      ]
    );
  };
}
