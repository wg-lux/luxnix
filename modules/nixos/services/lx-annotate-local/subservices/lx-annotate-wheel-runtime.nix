# Purpose: Define only the lx-annotate-wheel-runtime.service unit.
# Command: lx-annotate-runtime-ensure.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-wheel-runtime = mkIf useWheelRuntime {
    description = "Prepare the shared LX-Annotate wheel runtime";
    before = [ "lx-annotate-migrate.service" ];
    after = [ "lx-annotate-runtime-env.service" ];
    wants = [ "lx-annotate-runtime-env.service" ];
    requires = [ "lx-annotate-runtime-env.service" ];
    restartTriggers = [ effectiveRuntimePackage ];
    serviceConfig = {
      Type = "oneshot";
      # Do not let a successful preparation for the previous package remain
      # active across an interrupted switch. Application start transactions
      # must run the idempotent stamp check for the currently selected wheel.
      RemainAfterExit = false;
      User = endoreg-service-user-name;
      Group = endoreg-service-group-name;
      WorkingDirectory = runtimeDataRootPath;
      ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-runtime-ensure";
      LogNamespace = lxAnnotateJournalNamespace;
      TimeoutStartSec = "2h";
    };
  };
}
