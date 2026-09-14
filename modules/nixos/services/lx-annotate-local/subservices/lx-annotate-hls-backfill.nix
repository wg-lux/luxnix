# Purpose: Define only the lx-annotate-hls-backfill.service unit.
# Command: runLxAnnotateHlsMaterialization with backfill arguments.
{ ctx }:
with ctx;
let
  hlsBackfillAllowedScript = pkgs.writeShellScript "lx-annotate-hls-backfill-allowed" ''
    if ${lib.escapeShellArg "${effectiveRuntimePackage}/bin/lx-annotate-manage"} shell --command ${lib.escapeShellArg ''
      from endoreg_db.models import UploadJob
      raise SystemExit(
          75
          if UploadJob.objects.filter(
              status__in=["pending", "processing", "retrying"],
          ).exists()
          else 0
      )
    ''}; then
      exit 0
    else
      condition_status=$?
      # ExecCondition treats 1..254 as a successful skip. Reserve 75 for
      # active imports and make actual runtime/database errors fail the unit.
      if [ "$condition_status" -eq 75 ]; then
        exit 1
      fi
      exit 255
    fi
  '';
in
{
  systemd.services.lx-annotate-hls-backfill = mkIf cfg.hlsBackfill.enable (mkLxAnnotateAppService {
    description = "Dispatch local encrypted HLS backfill for LX-Annotate videos";
    wantedBy = [ "multi-user.target" ];
    # Corpus reconciliation must never gate the web or its cryptographic
    # preflight. Start it only after the application and queue consumer start.
    after = [
      "lx-annotate.service"
      "lx-annotate-preflight.service"
      "lx-annotate-celery-ffmpeg-worker.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ]
    ++ localRedisServiceUnits;
    wants = [
      "lx-annotate-load-base-data.service"
    ];
    requires = [
      "lx-annotate-preflight.service"
      "lx-annotate-celery-ffmpeg-worker.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ]
    ++ localRedisServiceUnits;
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
