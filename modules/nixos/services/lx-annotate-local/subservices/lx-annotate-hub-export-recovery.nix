# Purpose: Define only the lx-annotate-hub-export-recovery.service unit and its matching triggers.
# Command: lx-annotate-manage dispatch_hub_export_recovery.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-hub-export-recovery =
    mkIf cfg.hub.outboundTransfer.enable
      (mkLxAnnotateAppService {
        description = "Dispatch bounded recovery for LX-Annotate outbound hub transfers";
        wantedBy = [ ];
        after = [
          "network-online.target"
          "lx-annotate-celery-hub-transfer-worker.service"
        ];
        wants = [
          "network-online.target"
          "lx-annotate-celery-hub-transfer-worker.service"
        ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-manage dispatch_hub_export_recovery";
          TimeoutStartSec = "2m";
        };
      });

  systemd.timers.lx-annotate-hub-export-recovery = mkIf cfg.hub.outboundTransfer.enable {
    description = "Periodically recover LX-Annotate outbound hub transfers";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "5m";
      OnUnitActiveSec = cfg.hub.outboundTransfer.recoveryInterval;
      RandomizedDelaySec = "30s";
      Persistent = true;
      Unit = "lx-annotate-hub-export-recovery.service";
    };
  };
}
