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
    users.users = {
      keycloak = {
        # isNormalUser = true;
        # home = cfg.homeDir;
        # createHome = true;
        # shell = "/sbin/nologin";
        # hashedPasswordFile = "${cfg.dbPasswordfile}_hash";
        # isNormalUser = true;
        # isSystemUser = true;
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

    systemd.services.keycloak-prepare-secret = {
      description = "Copy Keycloak DB password file with correct permissions";
      wantedBy = [ "multi-user.target" ];
      # Runs only once on boot
      serviceConfig.ExecStart = ''
        ${pkgs.coreutils}/bin/cp /etc/secrets/vault/${cfg.dbPasswordfile} ${cfg.homeDir}/db-password
        ${pkgs.coreutils}/bin/chown keycloak:keycloak ${cfg.homeDir}/db-password
        ${pkgs.coreutils}/bin/chmod 0600 ${cfg.homeDir}/db-password
      '';
    };

    systemd.services.keycloak.wants = [ "openvpn-aglNet.service" "keycloak-prepare-secret.service" ];
    systemd.services.keycloak.after = [ "openvpn-aglNet.service" "keycloak-prepare-secret.service" ];

    # systemd.services.keycloak = {
    #     wants = [ "openvpn-aglNet.service" "network-online.target" ];
    #     after = [ "openvpn-aglNet.service" "network-online.target" ];
    #     serviceConfig = {
    #     # Add a pre-start script to check for database connectivity
    #     ExecStartPre = pkgs.writeScript "check-db-connectivity.sh" ''
    #         #!/bin/sh
    #         until ${pkgs.netcat}/bin/nc -z ${conf.database.host} ${toString conf.database.port}; do
    #         echo "Waiting for database connectivity..."
    #         sleep 1
    #         done
    #     '';
    #     };
    # };

    services.keycloak = {
      enable = true;
      initialAdminPassword = cfg.adminInitialPassword;
      database = {
        createLocally = false;
        username = cfg.dbUsername; # 
        # useSSL = false; #FIXME harden
        passwordFile = "${cfg.homeDir}/db-password";
        # Add explicit type to ensure proper database configuration
        type = "postgresql";

        host = "localhost";
        name = cfg.dbUsername; # defaults to keycloak
        port = config.services.postgresql.settings.port;
      };
      settings = {
        http-host = "0.0.0.0";  # Listen on all interfaces
        # http-host = "localhost";  # Listen on all interfaces
        http-port = cfg.httpPort;
        http-enabled = true;  # Explicitly enable HTTP
        hostname = "http://${cfg.hostname}"; # remove leading 'https://'
        hostname-admin = "https://${cfg.hostnameAdmin}";
        hostname-strict = false;
        hostname-strict-https = false;
        hostname-backchannel-dynamic = true;
      };
    };

    systemd.services.keycloak.environment = {
      CREDENTIALS_DIRECTORY = "${cfg.homeDir}/";
    };

    networking.firewall.allowedTCPPorts = [ cfg.httpPort ];
    # allow port on tun0
    # networking.firewall.interfaces.tun0.allowedTCPPorts = [ cfg.httpPort ]; #FIXME #TODO tun0 should be automatically inferred from defined vpn
  
  };

}
