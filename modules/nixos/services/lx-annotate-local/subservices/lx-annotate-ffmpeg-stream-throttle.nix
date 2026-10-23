# Purpose: Define only the lx-annotate-ffmpeg-stream-throttle.service unit and its matching triggers.
# Command: ffmpegStreamThrottleScript reconciles FFmpeg worker cgroup controls.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-ffmpeg-stream-throttle = mkIf cfg.runtime.ffmpegStreamThrottle.enable {
    description = "Apply stream-aware runtime throttling to the LX-Annotate FFmpeg worker";
    after = [
      "lx-annotate-runtime-env.service"
      "lx-annotate-migrate.service"
      ffmpegStreamThrottleWorkerUnit
    ]
    ++ localPostgresServiceUnits
    ++ localPostgresSetupUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    wants = [
      "lx-annotate-runtime-env.service"
    ]
    ++ localPostgresServiceUnits
    ++ localPostgresSetupUnits
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    requires = [
      "lx-annotate-runtime-env.service"
    ]
    ++ managedSecretsSetupUnits
    ++ encryptionServiceUnits;
    unitConfig = encryptedDataMountUnitConfig;
    environment = commonExtraEnv;
    serviceConfig = {
      Type = "oneshot";
      WorkingDirectory = runtimeDataRootPath;
      EnvironmentFile = envSystemdFilePath;
      ExecStart = ffmpegStreamThrottleScript;
      ProtectSystem = "full";
      PrivateTmp = true;
      NoNewPrivileges = true;
      ReadWritePaths = appReadWritePaths ++ [ "/run/lx-annotate" ];
    };
    path = [
      pkgs.coreutils
      pkgs.systemd
    ];
  };

  systemd.timers.lx-annotate-ffmpeg-stream-throttle = mkIf cfg.runtime.ffmpegStreamThrottle.enable {
    description = "Periodically reconcile stream-aware FFmpeg worker throttling";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = cfg.runtime.ffmpegStreamThrottle.interval;
      OnUnitActiveSec = cfg.runtime.ffmpegStreamThrottle.interval;
      AccuracySec = "10s";
      Unit = "lx-annotate-ffmpeg-stream-throttle.service";
    };
  };
}
