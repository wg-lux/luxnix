{
  config,
  lib,
  pkgs,
  ...
}:
#CHANGEME
with lib; 
with lib.luxnix; let
  cfg = config.services.luxnix.postgresql;
  enableKeycloak = config.roles.keycloakHost.enable;
  keycloakDbUser = config.roles.keycloakHost.dbUsername;

  auth = cfg.authentication + 
      (if keycloakDbUser then "\nhost ${keycloakDbUser} ${keycloakDbUser} 127.0.0.1/32 scram-sha-256" else "");

  identMap = cfg.identMap;

in {
  options.services.luxnix.postgresql = {
    enable = mkBoolOpt false "Enable postgresql";
    backupLocation = mkOption {
      type = types.str;
      default = "/home/${config.user.admin.name}/postgresql-backup";
    };

    authentication = mkOption {
      # multi line string
      type = types.str;
      default = ''
        #type database                  DBuser                      address                     auth-method         optional_ident_map
        local sameuser                  all                                                     peer                map=superuser_map
        host  all                       all
        host  replication               ${cfg.replUser}
        host  ${cfg.devUser}            ${cfg.devUser}
      '';
    };

    identMap = mkOption {
      type = types.str;
      default = ''
        # ArbitraryMapName systemUser DBUser
        superuser_map      root      postgres
        superuser_map      root      ${cfg.replUser}
        superuser_map      ${config.user.admin.name}     ${config.user.admin.name}
        superuser_map      ${config.user.admin.name}     endoregClient
        superuser_map      postgres  postgres

        # Let other names login as themselves
        superuser_map      /^(.*)$   \1           
      '' ;
    };
  };

  config = mkIf cfg.enable {

    # tmpfile rule for backup directory
    systemd.tmpfiles.rules = [
      "d ${cfg.backupLocation} 0700 postgres postgres -"
    ];

    environment.systemPackages = with pkgs; [
      postgresql_16_jit
    ];

    services = {

      postgresql = {
        enable = true;
        settings = {
          listen_addresses = "*";
        };
        # TODO: look at using default postgres
        package = pkgs.postgresql_16_jit;
        extensions = ps: with ps; [pgvecto-rs];
        settings = {
          shared_preload_libraries = ["vectors.so"];
          search_path = "\"$user\", public, vectors";
        };
        authentication = lib.mkOverride 100 auth;
        identMap = lib.mkOverride 100  identMap;
      };
      postgresqlBackup = {
        enable = true;
        location = "${cfg.backupLocation}";
        backupAll = true;
        startAt = "*-*-* 10:00:00";
      };
    };
  };
}
