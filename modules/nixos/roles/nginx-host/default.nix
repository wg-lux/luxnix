{ config, lib, pkgs, ... }:

with lib;
with lib.luxnix; let
  cfg = config.roles.nginxHost;
  conf = cfg.settings;
  vpnIp = config.luxnix.generic-settings.vpnIp;
  vpnSubnet = config.luxnix.generic-settings.vpnSubnet;
  sslCertGroupName = config.users.groups.sslCert.name;
  sensitiveServicesGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;

  networkConfig = config.luxnix.generic-settings.network;
  nginxConfig = networkConfig.nginx;
  keycloakConfig = networkConfig.keycloak;
  nextcloudConfig = networkConfig.nextcloud;
  psqlMainConfig = networkConfig.psqlMain;
  psqlTestConfig = networkConfig.psqlTest;

  nginx_cert_path = "/etc/nginx-host/ssl_cert";
  nginx_key_path = "/etc/nginx-host/ssl_key";

  all-extraConfig = ''
    proxy_headers_hash_bucket_size ${toString cfg.settings.proxyHeadersHashBucketSize};
    proxy_headers_hash_max_size ${toString cfg.settings.proxyHeadersHashMaxSize};
  '';

  intern-endoreg-net-extraConfig = ''
    allow ${vpnSubnet};
    deny all;
  '';

  # test add: X-NginX-Proxy true; proxy
  # removed:   proxy_ssl_server_name  # 

  ### OLD ONE
  # appendHttpConfig = ''
  #   proxy_set_header Host $host;
  #   proxy_set_header X-Forwarded-Host $host;
  #   proxy_set_header X-Forwarded-Proto $scheme;
  #   proxy_set_header X-Real-IP $remote_addr;
  #   proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  #   proxy_pass_header Authorization;
  #   proxy_ssl_server_name on;
  # '';
  ###

  # proxy_set_header X-Forwarded-Proto $scheme;
  appendHttpConfig = ''
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_pass_header Authorization;
  
    proxy_set_header X-NginX-Proxy true;
    add_header Strict-Transport-Security "max-age=15552000; includeSubDomains; preload";
  '';

  nginxPrepareScript = pkgs.writeScript "nginx-prepare-files.sh" ''
    #!/bin/sh
    set -e
    cp ${cfg.sslCertPath} ${nginx_cert_path}
    cp ${cfg.sslKeyPath} ${nginx_key_path}
    chown nginx:nginx ${nginx_cert_path} ${nginx_key_path}
    chmod 600 ${nginx_cert_path} ${nginx_key_path}
  '';
in
{
  #TODO MIGRATE DOMAIN SETTINGS TO GENERIC SETTINGS SO THAT THEY ARE AVAILABLE ON ALL MACHINES
  options.roles.nginxHost = {
    enable = mkBoolOpt false "Enable NGINX";
    sslCertPath = mkOpt types.path config.luxnix.generic-settings.sslCertificatePath "Path to SSL certificate";
    sslKeyPath = mkOpt types.path config.luxnix.generic-settings.sslCertificateKeyPath "Path to SSL key";
    keycloak = {
      enable = mkBoolOpt false "Enable Keycloak routing";
    };
    nextcloud = {
      enable = mkBoolOpt false "Enable Nextcloud routing";
    };
    psqlMain = {
      enable = mkBoolOpt false "Enable PostgreSQL main routing";
    };
    psqlTest = {
      enable = mkBoolOpt false "Enable PostgreSQL test routing";
    };

    settings = {

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
    users.groups."nginx" = { };

    # Allow default http and https ports
    networking.firewall.allowedTCPPorts = [
      80
      443
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
      virtualHosts = lib.mkMerge [
        (mkIf cfg.psqlMain.enable {
          #TODO domain in psql config
          "${psqlMainConfig.domain}" = {
            forceSSL = true;
            sslCertificate = nginx_cert_path;
            sslCertificateKey = nginx_key_path;

            locations."/" = {
              proxyPass = "https://${psqlMainConfig.vpnIp}:${toString psqlMainConfig.port}";
              extraConfig = all-extraConfig + intern-endoreg-net-extraConfig;
            };
          };
        })
        (mkIf cfg.psqlTest.enable {
          #TODO domain in psql config
          "${psqlTestConfig.domain}" = {
            forceSSL = true;
            sslCertificate = nginx_cert_path;
            sslCertificateKey = nginx_key_path;

            locations."/" = {
              proxyPass = "https://${psqlTestConfig.vpnIp}:${toString psqlTestConfig.port}";
              extraConfig = all-extraConfig + intern-endoreg-net-extraConfig;
            };
          };
        })
        (mkIf cfg.nextcloud.enable {
          "${nextcloudConfig.domain}" = {
            forceSSL = true;
            sslCertificate = nginx_cert_path;
            sslCertificateKey = nginx_key_path;

            # locations."/whiteboard/" = {
            #   proxyPass = "http://${nextcloudConfig.vpnIp}:3002/";
            #   proxy_http_version = "1.1";
            #   proxyWebsockets = true; #
            #   # proxy_set_header Upgrade $http_upgrade;
            #   # proxy_set_header Connection "Upgrade";
            #   extraConfig = all-extraConfig + ''
            #     proxy_set_header Upgrade $http_upgrade
            #     proxy_set_header Connection "Upgrade"'';
            # };

            locations."/" = {
              proxyPass = "http://${nextcloudConfig.vpnIp}/";
              extraConfig = all-extraConfig;
            };
          };
        })
        (mkIf cfg.keycloak.enable {
          "${keycloakConfig.domain}" = {
            forceSSL = true;
            sslCertificate = nginx_cert_path;
            sslCertificateKey = nginx_key_path;

            locations."/" = {
              proxyPass = "https://${keycloakConfig.vpnIp}:${toString keycloakConfig.port}";
              proxyWebsockets = true;
              extraConfig = all-extraConfig;
            };
          };

          "${keycloakConfig.adminDomain}" = {
            forceSSL = true;
            sslCertificate = nginx_cert_path;
            sslCertificateKey = nginx_key_path;

            locations."/" = {
              proxyPass = "https://${keycloakConfig.vpnIp}:${toString keycloakConfig.port}";
              extraConfig = all-extraConfig + intern-endoreg-net-extraConfig;
            };
          };

        })
      ];
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
