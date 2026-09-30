# Purpose: Define only the lx-annotate-hub-export-health.service unit and its matching triggers.
# Command: lx-annotate-manage check_hub_export_health.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-hub-export-health =
    mkIf cfg.hub.outboundTransfer.enable
      (mkLxAnnotateAppService {
        description = "Classify LX-Annotate outbound hub transfer health";
        wantedBy = [ ];
        after = [
          "lx-annotate-celery-hub-transfer-worker.service"
          "lx-annotate-hub-node-provisioning.service"
        ];
        wants = [ "lx-annotate-celery-hub-transfer-worker.service" ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-manage check_hub_export_health";
          TimeoutStartSec = "2m";
        };
      });

  systemd.timers.lx-annotate-hub-export-health = mkIf cfg.hub.outboundTransfer.enable {
    description = "Alert on classified LX-Annotate hub transfer failures";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "7m";
      OnUnitActiveSec = cfg.hub.outboundTransfer.recoveryInterval;
      RandomizedDelaySec = "30s";
      Persistent = true;
      Unit = "lx-annotate-hub-export-health.service";
    };
  };
}
