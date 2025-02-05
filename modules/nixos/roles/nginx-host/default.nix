{config, lib, pkgs, ...}: 

with lib; 
with lib.luxnix; let
  cfg = config.roles.nginxHost;
  conf = cfg.settings;
  vpnIp = config.luxnix.generic-settings.vpnIp;
  vpnSubnet = config.luxnix.generic-settings.vpnSubnet;

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

in {
  options.roles.nginxHost = {
    enable = mkBoolOpt false "Enable NGINX";
    sslCertPath = mkOpt types.path config.luxnix.generic-settings.sslCertificatePath "Path to SSL certificate";
    sslKeyPath = mkOpt types.path config.luxnix.generic-settings.sslCertificateKeyPath "Path to SSL key";
    keycloak = {
      enable = mkBoolOpt false "Enable Keycloak routing";
      domain = mkOpt types.str "keycloak.endo-reg.net" "Keycloak domain";
      adminDomain = mkOpt types.str "keycloak-admin.endo-reg.net" "Keycloak admin domain";
      port = mkOpt types.port 9080 "Keycloak HTTP port";
    };
    testPage = {
      enable = mkBoolOpt false "Enable test page";
      domain = mkOpt types.str "test.endo-reg.net" "Test page domain";
      port = mkOpt types.port 8081 "Test page port";
    };

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
      user = mkOption {
        type = types.str;
        default = "nginx";
        description = "User to run NGINX as";
      };
      extraGroups = mkOption {
        type = types.listOf types.str;
        default = [
          "wheel" "docker" "podman" "networkmanager" "sslCert" "sensitiveServices"
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

    # make sure the user exists
    users.extraUsers."${conf.user}" = {
      isSystemUser = true;
      group = "${conf.user}";
      extraGroups = conf.extraGroups;
    };

    # make sure the group exists
    users.groups."${conf.user}" = {};

    # Allow default http and https ports
        networking.firewall.allowedTCPPorts = [ 
            conf.ports.http conf.ports.https
     ];

    services.nginx = {
      enable = true;
      # user = "root";
      # user = "nginx";
      # user = conf.user; # should be "nginx"
      recommendedGzipSettings = conf.recommendedGzipSettings;
      recommendedOptimisation = conf.recommendedOptimisation;
      recommendedProxySettings = conf.recommendedProxySettings;
      recommendedTlsSettings = conf.recommendedTlsSettings;

      appendHttpConfig = appendHttpConfig;
      virtualHosts = {} // (if cfg.testPage.enable then {
        "${cfg.testPage.domain}" = {
          forceSSL = false;
          # forceSSL = true;
          sslCertificate = cfg.sslCertPath;
          sslCertificateKey = cfg.sslKeyPath;

          locations."/" = {
              proxyPass = "http://${vpnIp}:${toString cfg.testPage.port}";
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
        #       proxyPass = "http://${keycloak-host-vpn-ip}:${toString network.ports.keycloak.http}"; # TODO FIXME
        #       extraConfig = base.all-extraConfig + intern-endoreg-net-extraConfig;
        #   };
        # };

        # "${cfg.keycloak.domain}" = {
        #   forceSSL = true;
        #   sslCertificate = cfg.sslCertPath;
        #   sslCertificateKey = cfg.sslKeyPath;

        #   locations."/" = {
        #     proxyPass = "http://${keycloak-host-vpn-ip}:${toString network.ports.keycloak.http}"; # TODO FIXME
        #     extraConfig = base.all-extraConfig;
        #   };
        # };
      } else {});
    };

  };
}

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