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
      default = 9443;
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

    dbUsername = mkOption {
      type = types.str;
      default = "keycloak";
      description = "Database username for keycloak";
    };

    dbPasswordfile = mkOption {
      type = types.str;
      default = "/etc/secrets/vault/SCRT_roles_system_password_keycloak_host_password";
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
        home = "/var/lib/keycloak";
        createHome = true;
        # shell = "/sbin/nologin";
        isNormalUser = true;
        group = cfg.dbUsername;
        extraGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];
        # uid = cfg.uid;
      };
    };

    users.groups = {
      "${cfg.dbUsername}" = {
        gid = cfg.gid;
      };
    };

    services.postgresql.ensureDatabases = [ cfg.dbUsername ];

    services.keycloak = {
      enable = true;
      initialAdminPassword = cfg.adminInitialPassword;
      database = {
        # createLocally = true;
        username = cfg.dbUsername; # 
        # useSSL = false;
        passwordFile = "${cfg.dbPasswordfile}_service";

        host = "localhost";
        name = cfg.dbUsername; # defaults to keycloak
        port = config.services.postgresql.settings.port;
      };
      settings = {
        hostname = cfg.hostname;
        http-host = cfg.vpnIP;
        http-port = cfg.httpPort;
        https-port = cfg.httpsPort; 
        # proxy = conf.proxy;# edge
        domain = cfg.hostname; # currently "keycloak.endo-reg.net"
        domain-admin = cfg.hostnameAdmin; # currently "keycloak-admin.endo-reg.net"
      };
      sslCertificateKey = config.luxnix.generic-settings.sslCertificateKeyPath;
      sslCertificate = config.luxnix.generic-settings.sslCertificatePath;
    };


    networking.firewall.allowedTCPPorts = [ cfg.httpPort cfg.httpsPort ];
  };

}
