{
  config,
  lib,
  pkgs,
  ...
}:
with lib; 
with lib.luxnix; let

  sslCertGroupName = config.users.groups.sslCert.name;
  sensitiveServicesGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
  
  # Use the host's VPN IP since keycloak.vpnIp is not defined
  vpnIp = config.luxnix.generic-settings.network.hosts.s-02.ip-vpn or "127.0.0.1";

  cfg = config.roles.keycloakHost;
  conf = config.luxnix.generic-settings.network.keycloak;
  sslCertFile = config.luxnix.generic-settings.sslCertificatePath;
  sslKeyFile = config.luxnix.generic-settings.sslCertificateKeyPath;

  keycloakPrepareScript = pkgs.writeScript "keycloak-prepare-files.sh" ''
    #!/bin/sh
    set -e
    cp /etc/secrets/vault/${cfg.dbPasswordfile} ${cfg.homeDir}/db-password
    chown keycloak:keycloak ${cfg.homeDir}/db-password
    chmod 0600 ${cfg.homeDir}/db-password
    cp ${sslCertFile} ${cfg.homeDir}/tls.crt
    cp ${sslKeyFile} ${cfg.homeDir}/tls.key
    chown keycloak:keycloak ${cfg.homeDir}/tls.crt ${cfg.homeDir}/tls.key
    chmod 600 ${cfg.homeDir}/tls.crt ${cfg.homeDir}/tls.key
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
        ExecStart = "${keycloakPrepareScript}";
      };
    };

    systemd.services.keycloak.wants = [ "openvpn-aglNet.service" "keycloak-db-setup.service" "keycloak-prepare-files.service" ];
    systemd.services.keycloak.after = [ "openvpn-aglNet.service" "keycloak-db-setup.service" "keycloak-prepare-files.service" ];

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

    networking.firewall.allowedTCPPorts = [ conf.port ];
    # allow port on tun0 #TODO
    # networking.firewall.interfaces.tun0.allowedTCPPorts = [ cfg.httpPort ]; #FIXME #TODO tun0 should be automatically inferred from defined vpn
  
  };

}
