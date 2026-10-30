# Purpose: Define only the lx-annotate-wheel-runtime.service unit.
# Command: lx-annotate-runtime-ensure.
{ ctx }:
with ctx;
{

  systemd.services.lx-annotate-wheel-runtime = mkIf useWheelRuntime {
    description = "Prepare the shared LX-Annotate wheel runtime";
    before = [ "lx-annotate-migrate.service" ];
    after = [
      "lx-annotate-runtime-env.service"
    ]
    ++ lib.optional (cfg.runtime.wheelhousePath == null) "network-online.target";
    wants = [
      "lx-annotate-runtime-env.service"
    ]
    ++ lib.optional (cfg.runtime.wheelhousePath == null) "network-online.target";
    requires = [ "lx-annotate-runtime-env.service" ];
    restartTriggers = [ effectiveRuntimePackage ];
    # Preparation stays active through a switch's stop phase so timer and path
    # triggers from the outgoing generation cannot queue a stale preparation
    # run. The switch restarts it after daemon-reload, and Requires= propagates
    # that restart to every application unit, stopping each one before the new
    # wheel is installed. Every application entrypoint still checks the release
    # stamp itself and fails closed if this restart did not happen.
    stopIfChanged = false;
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      User = endoreg-service-user-name;
      Group = endoreg-service-group-name;
      WorkingDirectory = runtimeDataRootPath;
      ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-runtime-ensure";
      LogNamespace = lxAnnotateJournalNamespace;
      TimeoutStartSec = "2h";
    };
  };
}
