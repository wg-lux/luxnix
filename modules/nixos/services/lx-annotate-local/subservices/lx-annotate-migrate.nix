# Purpose: Define only the lx-annotate-migrate.service unit.
# Command: lx-annotate-manage migrate --noinput, with guarded legacy-history repair on failure.
{ ctx }:
with ctx;
let
  migrateWithLegacyHistoryFallback = pkgs.writeShellScript "lx-annotate-migrate-with-legacy-history-fallback" ''
    set -euo pipefail

    if ${effectiveRuntimePackage}/bin/lx-annotate-manage migrate --noinput; then
      exit 0
    fi

    echo "Initial migration failed; attempting reviewed legacy migration-history repair." >&2
    ${effectiveRuntimePackage}/bin/lx-annotate-manage shell --command \
      'from django.core.management import call_command; call_command("repair_legacy_migration_history", apply=True)'
    exec ${effectiveRuntimePackage}/bin/lx-annotate-manage migrate --noinput
  '';
in
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
      ExecStart = migrateWithLegacyHistoryFallback;
      TimeoutStartSec = "2h";
    };
  };
}
