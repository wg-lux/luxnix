{ config, lib, ... }:
let
  cfg = config.roles.postgres.default;
  pg = config.services.postgresql;
in
{
  options.roles.postgres.default.automaticCollationRepair =
    lib.mkEnableOption "rebuild indexes before refreshing changed database collations during local application startup";

  config = lib.mkIf (cfg.enable && cfg.automaticCollationRepair) {
    systemd.services.postgresql-collation-repair = {
      description = "Repair changed PostgreSQL database collations";
      requires = [
        "postgresql.service"
        "postgresql-setup.service"
      ];
      after = [
        "postgresql.service"
        "postgresql-setup.service"
      ];
      before = [ "postgres-endoreg-setup.service" ];
      serviceConfig = {
        Type = "oneshot";
        User = "postgres";
        Group = "postgres";
        TimeoutStartSec = "2h";
      };
      environment = {
        PGHOST = "/run/postgresql";
        PGPORT = toString pg.settings.port;
        PGUSER = pg.superUser;
        PGOPTIONS = "-c lock_timeout=30s -c statement_timeout=1h";
      };
      script = ''
        set -euo pipefail
        for database in ${
          lib.escapeShellArgs (
            lib.unique (
              [
                "postgres"
                "template1"
              ]
              ++ pg.ensureDatabases
            )
          )
        }; do
          ${pg.package}/bin/psql -X --no-password --dbname="$database" \
            --file=${./collation-repair.sql}
        done
      '';
    };
    systemd.services.postgres-endoreg-setup = {
      requires = [ "postgresql-collation-repair.service" ];
      after = [ "postgresql-collation-repair.service" ];
    };
  };
}
