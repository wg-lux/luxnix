# Purpose: Define only the lx-annotate-data-recovery.service unit.
# Command: runLxAnnotateDataRecovery.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-data-recovery = mkIf cfg.dataRecovery.enable (mkLxAnnotateAppService {
    description = "Recover legacy LX-Annotate data into the runtime storage root";
    wantedBy = [ ];
    before = [
      "lx-annotate-migrate.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${runLocalDataRecoveryScript}/bin/runLxAnnotateDataRecovery";
      TimeoutStartSec = "2h";
    };
  });
}
