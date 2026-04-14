{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let

  sensitiveServicesGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
  sslCertGroupName =
    if config.users.groups ? sslCert
    then config.users.groups.sslCert.name
    else sensitiveServicesGroupName;

  # Use the host's own VPN IP so keycloak can run on any host, not just s-02
  vpnIp = config.luxnix.generic-settings.vpnIp;
  cfg = config.roles.keycloakHost;
  conf = config.luxnix.generic-settings.network.keycloak;
  sslCertFile = config.luxnix.generic-settings.sslCertificatePath;
  sslKeyFile = config.luxnix.generic-settings.sslCertificateKeyPath;

  keycloakSyncScript = pkgs.writeScript "keycloak-sync-materials.sh" ''
    #!/bin/sh
    set -eu

    umask 077

    db_source="/etc/secrets/vault/${cfg.dbPasswordfile}"
    cert_source="${sslCertFile}"
    key_source="${sslKeyFile}"

    db_target="${cfg.homeDir}/db-password"
    cert_target="${cfg.homeDir}/tls.crt"
    key_target="${cfg.homeDir}/tls.key"

    install -d -m 770 -o keycloak -g ${sensitiveServicesGroupName} "${cfg.homeDir}"

    changed=0

    sync_file() {
      src="$1"
      dst="$2"
      mode="$3"

      if [ ! -e "$src" ]; then
        echo "Required file $src is missing" >&2
        exit 1
      fi

      if [ ! -e "$dst" ] || ! cmp -s "$src" "$dst"; then
        install -m "$mode" -o keycloak -g keycloak "$src" "$dst"
        changed=1
      fi
    }

    sync_file "$db_source" "$db_target" 600
    sync_file "$cert_source" "$cert_target" 600
    sync_file "$key_source" "$key_target" 600

    if [ "$changed" -eq 1 ] && systemctl is-active --quiet keycloak.service; then
      systemctl restart keycloak.service
    fi
  '';

  # Script to set up keycloak database user password
  setupKeycloakDbUser = pkgs.writeShellScript "setup-keycloak-db-user" ''
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

    # Ensure the password file exists (managed-secrets should have created it)
    if [ ! -f /etc/secrets/vault/${cfg.dbPasswordfile} ]; then
      echo "ERROR: Password file /etc/secrets/vault/${cfg.dbPasswordfile} not found"
      echo "Make sure managed-secrets service has run successfully"
      exit 1
    fi

    # Set the password in PostgreSQL safely using dollar-quoted strings
    echo "Setting password for user ${cfg.dbUsername}..."

    PASSWORD=$(cat /etc/secrets/vault/${cfg.dbPasswordfile})

    # Use dollar-quoted strings to safely handle any special characters
    ${config.services.postgresql.package}/bin/psql -U postgres -d postgres -c \
      "ALTER USER \"${cfg.dbUsername}\" WITH PASSWORD \$securepass\$''${PASSWORD}\$securepass\$;"

    echo "Keycloak database user password configured successfully"
  '';

  in {
  options.roles.keycloakHost = {
    enable = mkBoolOpt false "Enable keycloak";
    adminUsername = mkOption {
      type = types.str;
      default = "admin";
      description = "Admin username for keycloak";
    };

    adminInitialPassword = mkOption {
      type = types.str;
      default = "admin";
      description = "Admin initial password for keycloak";
    };

    homeDir = mkOption {
      type = types.str;
      default = "/etc/keycloak";
      description = "Home directory for keycloak";
    };

    dbUsername = mkOption {
      type = types.str;
      default = "keycloak";
      description = "Database username for keycloak";
    };

    dbPasswordfile = mkOption {
      type = types.str;
      default = "SCRT_roles_system_password_keycloak_host_password";
      # default = "/etc/secrets/vault/SCRT_roles_system_password_keycloak_host_password";
      # default = "/home/${cfg.dbUserName}/keycloak-db-password";
      description = "path to passwordfile for keycloak";
    };



    gid = mkOption {
      type = types.int;
      default = 600;
    };

    uid = mkOption {
      type = types.int;
      default = 600;
    };

  };

  config = mkIf cfg.enable {
    group.endoreg-service.enable = true; # enable endoreg-service group
    roles.managed-secrets.enable = true; # ensure managed secrets are enabled
    users.users = {
      keycloak = {
        group = "keycloak";
        extraGroups = [
          sslCertGroupName
          sensitiveServicesGroupName
          "networkmanager"
        ];
        uid = cfg.uid;
      };
    };

    users.groups = {
      keycloak = {
        gid = cfg.gid;
      };
    };

    # ensure db user and db exist
    services.postgresql.ensureUsers = [
      {
        name = cfg.dbUsername;
        ensureDBOwnership = true;
      }
    ];
    services.postgresql.ensureDatabases = [ cfg.dbUsername ];

    # Ensure password file permissions
    systemd.services.keycloak.serviceConfig = {
      User = "keycloak"; # hardcoded in keycloak nix package
      Group = "keycloak"; # hardcoded in keycloak nix package
      SupplementaryGroups = [
        sensitiveServicesGroupName
        # Network Management
        "${sslCertGroupName}"
        "networkmanager"
      ];
    };

    systemd.tmpfiles.rules = [
      "d ${cfg.homeDir} 0770 keycloak ${sensitiveServicesGroupName} -"
    ];

    # Set up keycloak database user password
    systemd.services.keycloak-db-setup = {
      description = "Set up Keycloak PostgreSQL user password";
      after = [ "postgresql.service" "managed-secrets-setup.service" ];
      requires = [ "postgresql.service" "managed-secrets-setup.service" ];
      before = [ "keycloak-prepare-files.service" ];
      wantedBy = [ "keycloak.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "root";
        ExecStart = setupKeycloakDbUser;
        # Retry if PostgreSQL isn't ready yet
        Restart = "on-failure";
        RestartSec = "5s";
        StartLimitBurst = 3;
      };
    };

    systemd.services.keycloak-prepare-files = {
      description = "Deploy DB password file and TLS certificates for Keycloak";
      after = [ "keycloak-db-setup.service" ];
      requires = [ "keycloak-db-setup.service" ];
      before = [ "keycloak.service" ];
      requiredBy = [ "keycloak.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = "${keycloakSyncScript}";
      };
    };

    systemd.services.keycloak-sync-materials = {
      description = "Synchronize Keycloak secrets and TLS material";
      after = [ "managed-secrets-setup.service" ];
      wants = [ "managed-secrets-setup.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = keycloakSyncScript;
      };
    };

    systemd.paths.keycloak-sync-materials = {
      description = "Watch for changes to Keycloak credential sources";
      wantedBy = [ "multi-user.target" ];
      pathConfig = {
        PathChanged = [
          "/etc/secrets/vault/${cfg.dbPasswordfile}"
          "${sslCertFile}"
          "${sslKeyFile}"
        ];
        Unit = "keycloak-sync-materials.service";
      };
    };

    systemd.timers.keycloak-sync-materials = {
      description = "Periodic Keycloak credential sync";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "15m";
        OnUnitActiveSec = "6h";
        Unit = "keycloak-sync-materials.service";
      };
    };

    systemd.services.keycloak.wants = [ "openvpn-aglnet.service" "keycloak-db-setup.service" "keycloak-prepare-files.service" ];
    systemd.services.keycloak.after = [ "openvpn-aglnet.service" "keycloak-db-setup.service" "keycloak-prepare-files.service" ];

    services.keycloak = {
      enable = true;
      initialAdminPassword = cfg.adminInitialPassword;
      database = {
        createLocally = false;
        username = cfg.dbUsername;
        # useSSL = false; #FIXME harden
        passwordFile = "${cfg.homeDir}/db-password";
        type = "postgresql";

        host = "localhost";
        name = cfg.dbUsername;
        port = config.services.postgresql.settings.port;
      };
      settings = {
        http-relative-path = "/";
        http-host = vpnIp;
        http-port = 8080;
        https-port = conf.port;
        https-certificate-file = "${cfg.homeDir}/tls.crt";
        https-certificate-key-file = "${cfg.homeDir}/tls.key";
        hostname = "https://${conf.domain}";
        # hostname-admin = "https://${conf.adminDomain}"; #FIXME
        hostname-port = conf.port;
        # hostname-admin-port = conf.port; #FIXME
        http-enabled = false;
        proxy-headers = "xforwarded";
        hostname-strict = false;
        hostname-strict-https = false;
        hostname-backchannel-dynamic = false;
      };
    };

    systemd.services.keycloak.environment = {
      CREDENTIALS_DIRECTORY = "${cfg.homeDir}/";
    };

    # Restrict keycloak port to VPN interface only — on a public-IP host (Hetzner),
    # keycloak must never be reachable from eth0. nginx proxies to it via tun0.
    networking.firewall.interfaces.tun0.allowedTCPPorts = [ conf.port ];

  };

}
