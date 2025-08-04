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

  # Safe PostgreSQL maintenance script package
  postgresMaintenanceScript = pkgs.writeScriptBin "postgres-maintenance" ''
    #!${pkgs.zsh}/bin/zsh
    set -e

    show_help() {
      echo "PostgreSQL Maintenance Script"
      echo "Usage: $0 [OPTION]"
      echo ""
      echo "Options:"
      echo "  --reset-psql       Reset PostgreSQL data (interactive confirmation required)"
      echo "  --show-psql-conf   Show PostgreSQL configuration"
      echo "  --help             Show this help message"
      echo ""
      echo "WARNING: Reset operations will permanently delete data!"
      echo "Make sure to backup your data before running any reset commands."
    }

    confirm_action() {
      local service="$1"
      local path="$2"
      echo "WARNING: This will permanently delete all $service data at $path"
      echo "This action cannot be undone!"
      echo -n "Are you sure you want to proceed? Type 'yes' to continue: "
      read confirmation
      if [ "$confirmation" != "yes" ]; then
        echo "Operation cancelled."
        exit 1
      fi
    }

    reset_postgresql() {
      local psql_dir="${cfg.postgresqlDataDir}"
      
      if [ ! -d "$psql_dir" ]; then
        echo "PostgreSQL data directory $psql_dir does not exist."
        return 0
      fi

      confirm_action "PostgreSQL" "$psql_dir"
      
      echo "Stopping PostgreSQL service..."
      sudo systemctl stop postgresql.service || true
      
      echo "Removing PostgreSQL data directory: $psql_dir"
      sudo rm -rf "$psql_dir"
      
      echo "PostgreSQL data has been reset."
      echo "Run: nixos-rebuild switch to reinitialize PostgreSQL."
    }

    show_psql_conf() {
      local psql_conf="${cfg.postgresqlDataDir}/postgresql.conf"
      if [ -f "$psql_conf" ]; then
        sudo cat "$psql_conf"
      else
        echo "PostgreSQL configuration file not found at: $psql_conf"
        echo "PostgreSQL may not be initialized yet."
      fi
    }

    case "''${1:-}" in
      --reset-psql)
        reset_postgresql
        ;;
      --show-psql-conf)
        show_psql_conf
        ;;
      --help|"")
        show_help
        ;;
      *)
        echo "Unknown option: $1"
        show_help
        exit 1
        ;;
    esac
  '';

  # Script to set up endoregDbLocal user password
  setupEndoregDbLocalUser = pkgs.writeShellScript "setup-endoreg-db-local-user" ''
    set -euo pipefail
    
    # Wait for PostgreSQL to be ready
    echo "Waiting for PostgreSQL to be ready..."
    for i in {1..30}; do
      if ${config.services.postgresql.package}/bin/pg_isready -U postgres -d postgres; then
        echo "PostgreSQL is ready"
        break
      fi
      if [ $i -eq 30 ]; then
        echo "ERROR: PostgreSQL not ready after 30 attempts"
        exit 1
      fi
      echo "Attempt $i: PostgreSQL not ready, waiting 2 seconds..."
      sleep 2
    done
    
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
    
    # Set the password in PostgreSQL safely using dollar-quoted strings
    # Dollar-quoting prevents SQL injection by treating the content as a literal string
    echo "Setting password for user ${cfg.defaultDbName}..."
    
    PASSWORD=$(cat ${endoregDbLocalPasswordFile})
    
    # Use dollar-quoted strings ($tag$...$tag$) which safely handle any special characters
    # including single quotes, backslashes, and other SQL metacharacters
    ${config.services.postgresql.package}/bin/psql -U postgres -d postgres -c \
      "ALTER USER \"${cfg.defaultDbName}\" WITH PASSWORD \$securepass\$''${PASSWORD}\$securepass\$;"
      
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
    # Add maintenance script to system packages
    environment.systemPackages = [ postgresMaintenanceScript ];

    services.luxnix.postgresql.enable = true;

    # Create systemd service to set up endoregDbLocal user password
    systemd.services.postgres-endoreg-setup = {
      description = "Set up endoregDbLocal PostgreSQL user password";
      after = [ "postgresql.service" ];
      requires = [ "postgresql.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "root";
        ExecStart = setupEndoregDbLocalUser;
        # Retry if PostgreSQL isn't ready yet
        Restart = "on-failure";
        RestartSec = "5s";
        StartLimitBurst = 3;
      };
    };

    # Create tmpfiles rule for password directory
    systemd.tmpfiles.rules = [
      "d /etc/secrets 0700 root root -"
      "d /etc/secrets/vault 0700 root root -"
    ];

    users.users = {
      postgres = {
        # Dont allow ssh access for postgres by default
        # But enable adding keys easily using postgres-default role
        openssh.authorizedKeys.keys = cfg.additionalPostgresAuthKeys;

      };
    };

    programs.zsh.shellAliases = {
      # Safe maintenance aliases that use the interactive maintenance script
      show-psql-conf = "postgres-maintenance --show-psql-conf";
      postgres-maintenance = "postgres-maintenance";
      # Interactive reset command with confirmation prompt
      reset-psql-safe = "postgres-maintenance --reset-psql";
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
