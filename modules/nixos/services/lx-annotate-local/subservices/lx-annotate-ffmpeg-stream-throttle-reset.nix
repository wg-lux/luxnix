# Purpose: Define only the lx-annotate-ffmpeg-stream-throttle-reset.service unit.
# Command: ffmpegStreamThrottleResetScript clears stale FFmpeg worker controls.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-ffmpeg-stream-throttle-reset =
    mkIf (!cfg.runtime.ffmpegStreamThrottle.enable)
      {
        description = "Reset runtime controls left by LX-Annotate FFmpeg stream throttling";
        wantedBy = [ "multi-user.target" ];
        after = [ ffmpegStreamThrottleWorkerUnit ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = ffmpegStreamThrottleResetScript;
          ProtectSystem = "full";
          PrivateTmp = true;
          NoNewPrivileges = true;
          ReadWritePaths = [ "/run/lx-annotate" ];
        };
      };
}
