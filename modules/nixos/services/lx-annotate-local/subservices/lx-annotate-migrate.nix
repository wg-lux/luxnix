# Purpose: Define only the lx-annotate-migrate.service unit.
# Command: lx-annotate-manage repair_legacy_migration_history, then migrate --noinput.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-migrate = mkLxAnnotateAppService {
    description = "Run LX-Annotate database migrations";
    before = [
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
      "lx-annotate.service"
    ];
    serviceConfig = {
      Type = "oneshot";
      ExecStartPre = "-${effectiveRuntimePackage}/bin/lx-annotate-manage repair_legacy_migration_history --apply";
      ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-manage migrate --noinput";
      TimeoutStartSec = "2h";
    };
  };
}
