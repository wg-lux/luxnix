# Purpose: Define only the lx-annotate-start-retry.service unit and its matching timer.
# Command: systemctl start --no-block for enabled long-running units that are inactive.
#
# systemd does not re-queue a start job cancelled with result "dependency". When
# Vault or encrypted storage becomes available only after boot, the preparation
# chain recovers but the web service and workers stay inactive. This timer queues
# the ordinary start job again; every Requires= gate still applies, so a unit
# whose prerequisites are still unmet stays down (fail closed).
{ ctx }:
with ctx;
let
  retryUnits = [
    "lx-annotate.service"
    "lx-annotate-celery-beat.service"
  ]
  ++ alwaysWorkerServiceUnits;
  startRetryScript = pkgs.writeShellScript "lx-annotate-start-retry" ''
    set -euo pipefail

    # Never race an activation: a start here could launch the outgoing generation.
    switch_lock=/run/nixos/switch-to-configuration.lock
    if [ -e "$switch_lock" ] && ! ${pkgs.util-linux}/bin/flock -n -s "$switch_lock" ${pkgs.coreutils}/bin/true; then
      echo "NixOS activation in progress; skipping start retry."
      exit 0
    fi

    for unit in ${lib.concatMapStringsSep " " lib.escapeShellArg retryUnits}; do
      state="$(${pkgs.systemd}/bin/systemctl show "$unit" --property=ActiveState --value)"
      # Only "inactive" is retried. "failed" is left for the unit's own Restart=
      # policy or operator review; it is never reset here.
      if [ "$state" = "inactive" ]; then
        echo "Queueing start for inactive unit $unit."
        ${pkgs.systemd}/bin/systemctl start --no-block "$unit"
      fi
    done
  '';
in
{
  systemd.services.lx-annotate-start-retry = {
    description = "Re-queue enabled LX-Annotate units left inactive after a failed start dependency";
    serviceConfig = {
      Type = "oneshot";
      User = "root";
      ExecStart = startRetryScript;
      TimeoutStartSec = "1m";
    };
  };

  # Stop this timer before deliberately stopping the web service or a worker for
  # maintenance; otherwise the unit is started again on the next interval.
  systemd.timers.lx-annotate-start-retry = {
    description = "Periodically retry starting inactive LX-Annotate web and worker units";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "3m";
      OnUnitActiveSec = "5m";
      RandomizedDelaySec = "30s";
      Unit = "lx-annotate-start-retry.service";
    };
  };
}
