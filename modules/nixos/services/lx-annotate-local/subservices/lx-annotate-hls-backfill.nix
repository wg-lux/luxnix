# Purpose: Define only the lx-annotate-hls-backfill.service unit.
# Command: runLxAnnotateHlsMaterialization with backfill arguments.
{ ctx }:
with ctx;
let
  hlsBackfillAllowedScript = pkgs.writeShellScript "lx-annotate-hls-backfill-allowed" ''
    exec ${lib.escapeShellArg "${effectiveRuntimePackage}/bin/lx-annotate-manage"} shell --command ${lib.escapeShellArg ''
      from endoreg_db.models import UploadJob
      raise SystemExit(
          1
          if UploadJob.objects.filter(
              status__in=["pending", "processing", "retrying"],
          ).exists()
          else 0
      )
    ''}
  '';
in
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
      # The import transaction temporarily exposes a processed file before its
      # synchronous raw/processed HLS finalization completes. A concurrent
      # backfill reservation would block that finalization, so defer the whole
      # corpus pass while any import is non-terminal.
      ExecCondition = "${hlsBackfillAllowedScript}";
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
