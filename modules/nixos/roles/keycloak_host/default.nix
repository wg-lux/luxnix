{
  config,
  lib,
  pkgs,
  ...
}:
with lib; 
with lib.luxnix; let

  cfg = config.roles.keycloakHost;

  in {
  options.roles.keycloakHost = {
    enable = mkBoolOpt false "Enable keycloak";

    httpPort = mkOption {
      type = types.int;
      default = 9080;
      description = "Port to run keycloak on";
    };

    httpsPort = mkOption {
      type = types.int;
      default = 9843;
      description = "Port to run keycloak on";
    };

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
      default = "/home/keycloak";
      description = "Home directory for keycloak";
    };

    dbUsername = mkOption {
      type = types.str;
      default = "keycloak";
      description = "Database username for keycloak";
    };

    dbPasswordfile = mkOption {
      type = types.str;
      default = "/etc/secrets/vault/SCRT_roles_system_password_keycloak_host_password";
      # default = "/etc/secrets/vault/SCRT_roles_system_password_keycloak_host_password";
      # default = "/home/${cfg.dbUserName}/keycloak-db-password";
      description = "path to passwordfile for keycloak";
    };

    hostname = mkOption {
      type = types.str;
      default = "keycloak.endo-reg.net";
      description = "Hostname for keycloak";
    };

    hostnameAdmin = mkOption {
      type = types.str;
      default = "keycloak-admin.endo-reg.net";
      description = "Hostname for keycloak admin";
    };

    vpnIP = mkOption {
      type = types.str;
      default = "172.16.255.3";
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
    services.postgresql.ensureUsers = [
      {
        name = cfg.dbUsername;
        ensureDBOwnership = true; # allows system users
      }  
    ];

    users.users = {
      keycloak = {
        # isNormalUser = true;
        # home = cfg.homeDir;
        # createHome = true;
        # shell = "/sbin/nologin";
        # hashedPasswordFile = "${cfg.dbPasswordfile}_hash";
        # isNormalUser = true;
        isSystemUser = true;
        group = cfg.dbUsername;
        extraGroups = [ 
          config.luxnix.generic-settings.sensitiveServiceGroupName 
          "sslCert"
          "networkmanager"  
        ];
        # uid = cfg.uid;
      };
    };

    users.groups = {
      "${cfg.dbUsername}" = {
        gid = cfg.gid;
      };
    };

    services.postgresql.ensureDatabases = [ cfg.dbUsername ];

    # Ensure password file permissions
    systemd.services.keycloak.serviceConfig = {
      SupplementaryGroups = [ 
        config.luxnix.generic-settings.sensitiveServiceGroupName
        # Network Management
        "networkmanager"  
      ];
    };

    # Ensure the password file exists and has correct permissions
    system.activationScripts.keycloakSetup = ''
      if [ -f ${cfg.dbPasswordfile} ]; then
        chown root:${config.luxnix.generic-settings.sensitiveServiceGroupName} ${cfg.dbPasswordfile}
        chmod 640 ${cfg.dbPasswordfile}
      fi
    '';

    services.keycloak = {
      enable = true;
      initialAdminPassword = cfg.adminInitialPassword;
      database = {
        createLocally = true;
        username = cfg.dbUsername; # 
        # useSSL = false; #FIXME harden
        passwordFile = "${cfg.dbPasswordfile}";
        # Add explicit type to ensure proper database configuration
        type = "postgresql";

        host = "localhost";
        name = cfg.dbUsername; # defaults to keycloak
        port = config.services.postgresql.settings.port;
      };
      settings = {
        hostname = cfg.hostname;
        http-host = "0.0.0.0";  # Listen on all interfaces
        http-port = cfg.httpPort;
        https-port = cfg.httpsPort;
        proxy-headers = ["forwarded" "x-forwarded-for" "x-forwarded-proto" "x-forwarded-host"];
        hostname-strict = false;
        hostname-strict-https = true;
        domain = cfg.hostname;
        domain-admin = cfg.hostnameAdmin;
      };
    };

    systemd.services.keycloak.environment = {
      CREDENTIALS_DIRECTORY = "/etc/secrets/vault";
    };

    networking.firewall.allowedTCPPorts = [ cfg.httpPort cfg.httpsPort ];
  
  };

}
