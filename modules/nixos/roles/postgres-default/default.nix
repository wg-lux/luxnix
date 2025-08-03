{ lib
, pkgs
, config
, ...
}:
with lib; let
  cfg = config.roles.postgres.default;

  # Password file paths
  endoregDbLocalPasswordFile = "/var/lib/postgresql/endoregDbLocal.password";
  maintenancePasswordFile = "/etc/secrets/vault/SCRT_local_password_maintenance_password";

  # Utility function to create attributes for a user
  mkDefaultUser = user: {
    name = user;
    ensureDBOwnership = true;
    ensureClauses = { };
  };

  # Script to set up endoregDbLocal user password
  setupEndoregDbLocalUser = pkgs.writeShellScript "setup-endoreg-db-local-user" ''
    set -euo pipefail
    
    # Create password if it doesn't exist
    if [ ! -f ${maintenancePasswordFile} ]; then
      echo "Generating password for endoregDbLocal user..."
      mkdir -p $(dirname ${maintenancePasswordFile})
      ${pkgs.openssl}/bin/openssl rand -base64 32 > ${maintenancePasswordFile}
      chmod 640 ${maintenancePasswordFile}
      chown root:${config.luxnix.generic-settings.sensitiveServiceGroupName} ${maintenancePasswordFile}
    fi
    
    # Ensure correct permissions on existing file
    chmod 640 ${maintenancePasswordFile}
    chown root:${config.luxnix.generic-settings.sensitiveServiceGroupName} ${maintenancePasswordFile}
    
    # Copy password for PostgreSQL access
    cp ${maintenancePasswordFile} ${endoregDbLocalPasswordFile}
    chown postgres:postgres ${endoregDbLocalPasswordFile}
    chmod 600 ${endoregDbLocalPasswordFile}
    
    # Set the password in PostgreSQL
    PASSWORD=$(cat ${endoregDbLocalPasswordFile})
    ${config.services.postgresql.package}/bin/psql -U postgres -d postgres -c \
      "ALTER USER ${cfg.defaultDbName} WITH PASSWORD '$PASSWORD';" || true
      
    echo "endoregDbLocal user password configured successfully"
  '';

in
{
  options.roles.postgres.default = {
    enable = mkEnableOption "Enable common configuration";
    postgresqlEnable = mkEnableOption "Enable PostgreSQL";
    postgresqlPort = mkOption {
      type = types.int;
      default = 5432;
    };

    replUser = mkOption {
      type = types.str;
      default = "replUser";
    };

    testUser = mkOption {
      type = types.str;
      default = "testUser";
    };

    devUser = mkOption {
      type = types.str;
      default = "devUser";
    };

    lxClientUser = mkOption {
      type = types.str;
      default = "lxClientUser";
    };

    stagingUser = mkOption {
      type = types.str;
      default = "stagingUser";
    };

    productionUser = mkOption {
      type = types.str;
      default = "prodUser";
    };

    defaultDbName = mkOption {
      type = types.str;
      default = "endoregDbLocal";
    };

    postgresqlDataDir = mkOption {
      type = types.str;
      default = "/var/lib/postgresql/${config.services.postgresql.package.psqlSchema}";
    };

    additionalPostgresAuthKeys = mkOption {
      type = types.listOf types.str;
      default = [ ];
      description = "Additional authorized keys for postgres user";
    };

  };


  config = mkIf cfg.enable {
    services.luxnix.postgresql.enable = true;

    # Create systemd service to set up endoregDbLocal user password
    systemd.services.postgres-endoreg-setup = {
      description = "Set up endoregDbLocal PostgreSQL user password";
      after = [ "postgresql.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "root";
        ExecStart = setupEndoregDbLocalUser;
      };
    };

    # Create tmpfiles rule for password directory
    systemd.tmpfiles.rules = [
      "d /etc/secrets 0755 root root -"
      "d /etc/secrets/vault 0755 root root -"
    ];

    users.users = {
      postgres = {
        # Dont allow ssh access for postgres by default
        # But enable adding keys easily using postgres-default role
        openssh.authorizedKeys.keys = cfg.additionalPostgresAuthKeys;

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
          cfg.defaultDbName
          "replication"
          cfg.replUser
          cfg.testUser
          cfg.devUser
          cfg.lxClientUser
          cfg.stagingUser
          cfg.productionUser
        ];

        ensureUsers = [
          {
            name = config.user.admin.name;
            ensureDBOwnership = true;
            ensureClauses = {
              replication = true;
            };
          }
          {
            name = cfg.defaultDbName;
            ensureDBOwnership = true;
            ensureClauses = {
              replication = true;
            };
          }

          (mkDefaultUser cfg.replUser)
          (mkDefaultUser cfg.testUser)
          (mkDefaultUser cfg.devUser)
          (mkDefaultUser cfg.lxClientUser)
          (mkDefaultUser cfg.stagingUser)
          (mkDefaultUser cfg.productionUser)
        ];

      };
    };



  };
}
