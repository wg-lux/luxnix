{config, lib, pkgs, ...}: 

with lib; 
with lib.luxnix; let
  cfg = config.roles.nginxHost;
  conf = cfg.settings;
  vpnIp = config.luxnix.generic-settings.vpnIp;
  vpnSubnet = config.luxnix.generic-settings.vpnSubnet;
  sslCertGroupName = config.users.groups.sslCert.name;
  sensitiveServicesGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
  
  networkConfig = config.luxnix.generic-settings.network;
  keycloakConfig = networkConfig.keycloak;
  nextcloudConfig = networkConfig.nextcloud;
  psqlMainConfig = networkConfig.psql-main;
  psqlTestConfig = networkConfig.psql-test;

  all-extraConfig = ''
      proxy_headers_hash_bucket_size ${toString cfg.settings.proxyHeadersHashBucketSize};
      proxy_headers_hash_max_size ${toString cfg.settings.proxyHeadersHashMaxSize};
  '';
  
  intern-endoreg-net-extraConfig = ''
      allow ${vpnSubnet};
      deny all;
  '';

  appendHttpConfig = ''
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-Host $host;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_ssl_server_name on;
      proxy_pass_header Authorization;
  '';

  nginxPrepareScript = pkgs.writeScript "nginx-prepare-files.sh" ''
    #!/bin/sh
    set -e
    cp ${cfg.sslCertPath} /etc/nginx-host/ssl_cert
    cp ${cfg.sslKeyPath} /etc/nginx-host/ssl_key
    chown nginx:nginx /etc/nginx-host/ssl_cert /etc/nginx-host/ssl_key
    chmod 600 /etc/nginx-host/ssl_cert /etc/nginx-host/ssl_key
  '';

in {
  options.roles.nginxHost = {
    enable = mkBoolOpt false "Enable NGINX";
    sslCertPath = mkOpt types.path config.luxnix.generic-settings.sslCertificatePath "Path to SSL certificate";
    sslKeyPath = mkOpt types.path config.luxnix.generic-settings.sslCertificateKeyPath "Path to SSL key";
    keycloak = {
      enable = mkBoolOpt false "Enable Keycloak routing";
      domain = mkOpt types.str "keycloak.endo-reg.net" "Keycloak domain";
      adminDomain = mkOpt types.str "keycloak-admin.endo-reg.net" "Keycloak admin domain";
    };
    nextcloud = {
      enable = mkBoolOpt false "Enable Nextcloud routing";
      domain = mkOpt types.str "cloud.endo-reg.net" "Nextcloud domain";
    };
    # psqlMain = {
    #   enable = mkBoolOpt false "Enable PostgreSQL main routing";
    #   domain = mkOpt types.str "psql-main.endo-reg.net" "PostgreSQL main domain";
    # };
    # psqlTest = {
    #   enable = mkBoolOpt false "Enable PostgreSQL test routing";
    #   domain = mkOpt types.str "psql-test.endo-reg.net" "PostgreSQL test domain";
    # };


    settings = {
      hostIp = mkOption {
        type = types.str;
        default = vpnIp;
        description = "IP address to bind NGINX to";
      };
      ports = {
        http = mkOption {
          type = types.int;
          default = 80;
          description = "Port to bind the NGINX to";
        };
        https = mkOption {
          type = types.int;
          default = 443;
          description = "Port to bind the NGINX to";
        };
      };
      proxyHeadersHashMaxSize = mkOption {
        type = types.int;
        default = 512;
        description = "Maximum size of the hash table for storing headers";
      };
      proxyHeadersHashBucketSize = mkOption {
        type = types.int;
        default = 64;
        description = "Size of the hash bucket for storing headers";
      };
      recommendedGzipSettings = mkOption {
        type = types.bool;
        default = true;
        description = "Enable recommended gzip settings";
      };
      recommendedOptimisation = mkOption {
        type = types.bool;
        default = true;
        description = "Enable recommended optimisation settings";
      };
      recommendedProxySettings = mkOption {
        type = types.bool;
        default = true;
        description = "Enable recommended proxy settings";
      };
      recommendedTlsSettings = mkOption {
        type = types.bool;
        default = true;
        description = "Enable recommended TLS settings";
      };

      extraGroups = mkOption {
        type = types.listOf types.str;
        default = [
          "wheel"
          "docker"
          "podman"
          "networkmanager"
          "${sslCertGroupName}"
          "${sensitiveServicesGroupName}"
        ];
        description = "Extra groups for the NGINX user";
      };
    };
  };

  config = mkIf cfg.enable {
    # if cfg.testPage is enabled, we should set up services.luxnix.testPage using our settings
    services.luxnix.testPage = {
      enable = cfg.testPage.enable;
      port = cfg.testPage.port;
    };

    # systemd.tmpfile.rule to make sure /etc/nginx-host exists
    systemd.tmpfiles.rules = [
      "d /etc/nginx-host 0700 nginx nginx -"
    ];

    systemd.services.nginx-prepare-files = {
      description = "Deploy SSL certificate and key for NGINX";
      before = [ "nginx.service" ];
      requiredBy = [ "nginx.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = "${nginxPrepareScript}";
      };
    };

    systemd.services.nginx.wants = [ "nginx-prepare-files.service" ];
    systemd.services.nginx.after = [ "nginx-prepare-files.service" ];

    # make sure the user exists
    users.extraUsers."nginx" = {
      isSystemUser = true;
      group = "nginx";
      extraGroups = conf.extraGroups;
    };

    # make sure the group exists
    users.groups."nginx" = {};

    # Allow default http and https ports
        networking.firewall.allowedTCPPorts = [ 
            conf.ports.http conf.ports.https
     ];

    services.nginx = {
      enable = true;
      user = "nginx";
      group = "nginx";
      recommendedGzipSettings = conf.recommendedGzipSettings;
      recommendedOptimisation = conf.recommendedOptimisation;
      recommendedProxySettings = conf.recommendedProxySettings;
      recommendedTlsSettings = conf.recommendedTlsSettings;

      appendHttpConfig = appendHttpConfig;
      virtualHosts = {} 
      // (if cfg.nextcloud.enable then {
        "${cfg.nextcloud.domain}" = {
          forceSSL = true;
          sslCertificate = cfg.sslCertPath;
          sslCertificateKey = cfg.sslKeyPath;

          locations."/" = {
              proxyPass = "https://${nextcloudConfig.vpnIp}:${toString nextcloudConfig.port}";
              extraConfig = all-extraConfig;
          };
        };
      } else {})
      // (if cfg.keycloak.enable then {
        # "${cfg.keycloak.adminDomain}" = {
        #   forceSSL = true;
        #   sslCertificate = cfg.sslCertPath;
        #   sslCertificateKey = cfg.sslKeyPath;

        #   locations."/" = {
        #       # proxyPass = "http://${keycloakConfig.vpnIp}:${toString keycloakConfig.port}";
        #       proxyPass = "http://172.16.255.12:9080";
        #       extraConfig = base.all-extraConfig + intern-endoreg-net-extraConfig;
        #   };
        # };

        "${cfg.keycloak.domain}" = {
          forceSSL = true;
          sslCertificate = cfg.sslCertPath;
          sslCertificateKey = cfg.sslKeyPath;

          locations."/" = {
            proxyPass = "https://${keycloakConfig.vpnIp}:${toString keycloakConfig.port}";
            extraConfig = all-extraConfig;
          };
        };
      } else {});
    };

  };
}


    # keycloak = {
    #   enable = mkBoolOpt false "Enable Keycloak routing";
    #   domain = mkOpt types.str "keycloak.endo-reg.net" "Keycloak domain";
    #   adminDomain = mkOpt types.str "keycloak-admin.endo-reg.net" "Keycloak admin domain";
    #   port = mkOpt types.port 9080 "Keycloak HTTP port";
    # };

##### FOR REFERENCE 
# "drive-intern.endo-reg.net" = {
    # forceSSL = true;
    # sslCertificate = sslCertificatePath;
    # sslCertificateKey = sslCertificateKeyPath;
    # locations."/" = {
    #     proxyPass = "https://${agl-network-config.services.synology-drive.ip}:${toString agl-network-config.services.synology-drive.port}";
    #     extraConfig = all-extraConfig +  intern-endoreg-net-extraConfig;
    #     proxyWebsockets = true;
    # };
    # extraConfig = ''
    #     client_max_body_size 100000M;
    # '';
# };