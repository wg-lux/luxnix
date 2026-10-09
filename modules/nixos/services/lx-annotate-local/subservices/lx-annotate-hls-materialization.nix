# Purpose: Define only the lx-annotate-hls-materialization.service unit.
# Command: runLxAnnotateHlsMaterialization with configured arguments.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-hls-materialization =
    mkIf cfg.hlsMaterialization.enable
      (mkLxAnnotateAppService {
        description = "Dispatch local encrypted HLS materialization for LX-Annotate videos";
        wantedBy = [ ];
        after = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
          ffmpegStreamThrottleWorkerUnit
        ];
        wants = [
          "lx-annotate-load-base-data.service"
          ffmpegStreamThrottleWorkerUnit
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
            ++ cfg.hlsMaterialization.extraArgs
          );
          TimeoutStartSec = cfg.hlsMaterialization.timeoutStartSec;
          Nice = 15;
          IOSchedulingClass = "best-effort";
          IOSchedulingPriority = 6;
        };
      });
}
