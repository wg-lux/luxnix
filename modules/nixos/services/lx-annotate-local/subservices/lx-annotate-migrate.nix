# Purpose: Define only the lx-annotate-migrate.service unit.
# Command: Schema migration with guarded legacy-history repair, then backend PTS backfill.
{ ctx }:
with ctx;
let
  migrateWithLegacyHistoryFallback = pkgs.writeShellScript "lx-annotate-migrate-with-legacy-history-fallback" ''
    set -euo pipefail

    ${effectiveRuntimePackage}/bin/lx-annotate-manage check_migration_compatibility
    if ${effectiveRuntimePackage}/bin/lx-annotate-manage migrate --noinput; then
      :
    else
      migration_status=$?
      # LX-Annotate reserves 3 for its post-schema presentation timestamp backfill.
      if [ "$migration_status" -eq 3 ]; then
        echo "Video timestamp backfill failed; schema-history repair is not applicable." >&2
        exit "$migration_status"
      fi

      echo "Initial migration failed; attempting reviewed legacy migration-history repair." >&2
      ${effectiveRuntimePackage}/bin/lx-annotate-manage check_migration_compatibility
      ${effectiveRuntimePackage}/bin/lx-annotate-manage shell --command \
        'from django.core.management import call_command; call_command("repair_legacy_migration_history", apply=True)'
      ${effectiveRuntimePackage}/bin/lx-annotate-manage migrate --noinput
    fi

    # Required for published wheels predating the application's migration hook.
    # The backend is idempotent when the application already recovered timelines.
    exec ${effectiveRuntimePackage}/bin/lx-annotate-manage backfill_video_timelines --apply
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
    stopIfChanged = false;
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = migrateWithLegacyHistoryFallback;
      TimeoutStartSec = "2h";
    };
  };
}
