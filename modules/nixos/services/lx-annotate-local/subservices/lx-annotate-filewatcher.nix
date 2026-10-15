# Purpose: Define only the lx-annotate-filewatcher.service unit and its matching triggers.
# Command: lx-annotate-watch --once.
{ ctx }:
with ctx;
{
  systemd = {
    services.lx-annotate-filewatcher = mkLxAnnotateAppService {
      description = "Process pending LX-Annotate import files";
      wantedBy = [ ];
      after = [
        "lx-annotate-load-base-data.service"
        "lx-annotate-master-key-check.service"
      ];
      wants = [ "lx-annotate-load-base-data.service" ];
      requires = [
        "lx-annotate-load-base-data.service"
        "lx-annotate-master-key-check.service"
      ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-watch --once";
        Restart = "no";
      };
    };
    timers.lx-annotate-filewatcher = {
      description = "Periodically retry pending LX-Annotate import files";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "2m";
        OnUnitActiveSec = "5m";
        RandomizedDelaySec = "30s";
        Persistent = true;
        Unit = "lx-annotate-filewatcher.service";
      };
    };
    paths.lx-annotate-filewatcher = {
      description = "Trigger LX-Annotate file watcher when import files arrive";
      wantedBy = [ "multi-user.target" ];
      pathConfig = {
        PathChanged = [
          runtimeWatcherVideoDirPath
          runtimeWatcherReportDirPath
          runtimeWatcherPreanonymizedDirPath
        ];
        Unit = "lx-annotate-filewatcher.service";
        MakeDirectory = true;
      };
    };
  };
}
