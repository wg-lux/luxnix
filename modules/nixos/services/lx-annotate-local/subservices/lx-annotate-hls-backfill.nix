# Purpose: Define only the lx-annotate-hls-backfill.service unit.
# Command: runLxAnnotateHlsMaterialization with backfill arguments.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-hls-backfill = mkIf cfg.hlsBackfill.enable (mkLxAnnotateAppService {
    description = "Dispatch local encrypted HLS backfill for LX-Annotate videos";
    wantedBy = [ "multi-user.target" ];
    before = [ "lx-annotate.service" ];
    after = [
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ];
    wants = [
      "lx-annotate-load-base-data.service"
    ];
    requires = [
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = lib.escapeShellArgs (
        [
          "${runLocalHlsMaterializationScript}/bin/runLxAnnotateHlsMaterialization"
        ]
        ++ cfg.hlsBackfill.extraArgs
      );
      TimeoutStartSec = cfg.hlsBackfill.timeoutStartSec;
      Nice = 15;
      IOSchedulingClass = "best-effort";
      IOSchedulingPriority = 6;
    };
  });

  systemd.timers.lx-annotate-hls-backfill = mkIf cfg.hlsBackfill.enable {
    description = "Reconcile prerequisite raw and processed HLS without operator action";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      Unit = "lx-annotate-hls-backfill.service";
      OnBootSec = "15m";
      OnUnitInactiveSec = "1h";
      RandomizedDelaySec = "5m";
      Persistent = true;
    };
  };
}
