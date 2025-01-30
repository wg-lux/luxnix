{
  lib,
  pkgs,
  config,
  ...
}:
with lib; let
  cfg = config.roles.postgres.default;
  defaultAuthKeys = config.users.users.${config.user.admin.name}.openssh.authorizedKeys.keys;
in {
  options.roles.postgres.default = {
    enable = mkEnableOption "Enable common configuration";
    postgresqlEnable = mkEnableOption "Enable PostgreSQL";
    postgresqlPort = mkOption {
      type = types.int;
      default = 5432;
    };

    postgresSshAuthorizedKeys = mkOption {
      type = types.listOf types.str;
      default = defaultAuthKeys;
    };

    postgresqlDataDir = mkOption {
      type = types.str;
      default = "/var/lib/postgresql/${config.services.postgresql.package.psqlSchema}";
    };

  };


  config = mkIf cfg.enable {
    services.luxnix.postgresql.enable = true;

    users.users = {
      postgres = {
        # isSystemUser = true;
        # home = "/var/lib/postgresql";
        # createHome = false;
        # shell = "/run/current-system/sw/bin/nologin";
        openssh.authorizedKeys.keys = cfg.postgresSshAuthorizedKeys;
      };
    };

    programs.zsh.shellAliases = {
      show-psql-conf = "sudo cat ${cfg.postgresqlDataDir}/postgresql.conf";
      reset-psql = "sudo rm -rf ${cfg.postgresqlDataDir}"; #TODO Add to documentation
    };

    services = {
      postgresql = {
        enableTCPIP = true;
        dataDir = cfg.postgresqlDataDir;
        settings = {
          port = lib.mkDefault cfg.postgresqlPort;
          listen_addresses = lib.mkDefault "localhost,127.0.0.1";
          wal_level = lib.mkDefault "replica";
          max_wal_senders = lib.mkDefault 5;
          wal_keep_size = lib.mkDefault "512MB";
          password_encryption = "scram-sha-256";
          # hot_standby = true;
          # log_connections = true;
          # log_statement = "all";
          # logging_collector = true;
          # log_disconnections = true;
          # log_destination = "syslog";
        };
        ensureDatabases = [ 
            config.user.admin.name
        ];

        ensureUsers = [
          {
            name = config.user.admin.name;
            ensureDBOwnership = true;
            ensureClauses = {
              replication = true;
            };
          }
          # {
          #   name = cfg.replUser;
          #   ensureDBOwnership = true;
          #   ensureClauses = {
          #     replication = true;
          #   };
          # }
        ];
        
        # host  ${conf.keycloak-user}     ${conf.keycloak-user}       127.0.0.1/32                scram-sha-256 
        # host  ${conf.keycloak-user}     ${conf.keycloak-user}       ${conf.host-keycloak-ip}/32 scram-sha-256
        # host  replication               ${cfg.replUser}              ${conf.ip-backup}/32        scram-sha-256
        # host  ${conf.users.aglnet-base.name} ${conf.users.aglnet-base.name} 172.16.255.142/32 scram-sha-256
        
        authentication = lib.mkOverride 10 config.luxnix.generic-settings.postgres.activeAuthentication;

        identMap = lib.mkOverride 10 config.luxnix.generic-settings.postgres.activeIdentMap;
      };
    };




  };
}
