{
  config,
  lib,
  pkgs,
  ...
}:

with lib;
with lib.luxnix;
let
  cfg = config.roles.nginxHost;
  conf = cfg.settings;
  vpnIp = config.luxnix.generic-settings.vpnIp;
  vpnSubnet = config.luxnix.generic-settings.vpnSubnet;
  sensitiveServicesGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
  sslCertGroupName =
    if config.users.groups ? sslCert then
      config.users.groups.sslCert.name
    else
      sensitiveServicesGroupName;

  networkConfig = config.luxnix.generic-settings.network;
  nginxConfig = networkConfig.nginx;
  keycloakConfig = networkConfig.keycloak;
  nextcloudConfig = networkConfig.nextcloud;
  glm52Config = networkConfig.glm52;
  psqlMainConfig = networkConfig.psqlMain;
  psqlTestConfig = networkConfig.psqlTest;

  nginxStateDir = "/etc/nginx-host";
  nginxSecretsDir = "${nginxStateDir}/secrets";
  nginx_cert_path = "${nginxStateDir}/ssl_cert";
  nginx_key_path = "${nginxStateDir}/ssl_key";
  fileBackedTlsEnabled =
    cfg.psqlMain.enable
    || cfg.psqlTest.enable
    || cfg.nextcloud.enable
    || (cfg.glm52.enable && !cfg.glm52.acme.enable)
    || cfg.keycloak.enable;

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
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_pass_header Authorization;

    proxy_set_header X-NginX-Proxy true;
    add_header Strict-Transport-Security "max-age=15552000; includeSubDomains; preload";

    proxy_set_header X-SSL-Client-Verify $ssl_client_verify;
    proxy_set_header X-SSL-Client-S-DN   $ssl_client_s_dn;
  '';

  nginxSyncScript = pkgs.writeScript "nginx-sync-certificates.sh" ''
    #!/bin/sh
    set -eu

    install -d -m 700 -o nginx -g nginx "${nginxStateDir}"

    NEEDS_RELOAD=0

    sync_file() {
      src="$1"
      dst="$2"

      if [ ! -e "$src" ]; then
        echo "Source certificate $src not found" >&2
        exit 1
      fi

      if [ ! -e "$dst" ] || ! cmp -s "$src" "$dst"; then
        install -m 600 -o nginx -g nginx "$src" "$dst"
        NEEDS_RELOAD=1
      fi
    }

    sync_file "${cfg.sslCertPath}" "${nginx_cert_path}"
    sync_file "${cfg.sslKeyPath}" "${nginx_key_path}"

    if [ "$NEEDS_RELOAD" -eq 1 ] && systemctl is-active --quiet nginx.service; then
      systemctl reload nginx.service
    fi
  '';

  glm52Oauth2ProxyEnvScript = pkgs.writeShellScript "glm-5-2-oauth2-proxy-env" ''
    set -eu

    client_secret_file="${cfg.glm52.oauth2.clientSecretFile}"
    cookie_secret_file="${cfg.glm52.oauth2.cookieSecretFile}"
    key_file="${cfg.glm52.oauth2.keyFile}"

    ${pkgs.coreutils}/bin/install -d -m 0700 -o nginx -g nginx "${nginxStateDir}"
    ${pkgs.coreutils}/bin/install -d -m 0700 -o root -g root "${nginxSecretsDir}"

    if [ ! -s "$client_secret_file" ]; then
      echo "Missing Keycloak client secret: $client_secret_file" >&2
      echo "Create a confidential Keycloak client named ${cfg.glm52.oauth2.clientID} with redirect URI ${cfg.glm52.oauth2.redirectURL}, then put its secret in this file." >&2
      exit 1
    fi

    if [ ! -s "$cookie_secret_file" ]; then
      umask 077
      ${pkgs.openssl}/bin/openssl rand -hex 16 > "$cookie_secret_file"
      ${pkgs.coreutils}/bin/chown root:root "$cookie_secret_file"
      ${pkgs.coreutils}/bin/chmod 0600 "$cookie_secret_file"
    fi

    client_secret="$(${pkgs.coreutils}/bin/tr -d '\n' < "$client_secret_file")"
    cookie_secret="$(${pkgs.coreutils}/bin/tr -d '\n' < "$cookie_secret_file")"
    tmp="$(${pkgs.coreutils}/bin/mktemp "$key_file.tmp.XXXXXX")"

    {
      printf 'OAUTH2_PROXY_CLIENT_SECRET=%s\n' "$client_secret"
      printf 'OAUTH2_PROXY_COOKIE_SECRET=%s\n' "$cookie_secret"
    } > "$tmp"

    ${pkgs.coreutils}/bin/chown root:root "$tmp"
    ${pkgs.coreutils}/bin/chmod 0600 "$tmp"
    ${pkgs.coreutils}/bin/mv "$tmp" "$key_file"
  '';

in
{
  #TODO MIGRATE DOMAIN SETTINGS TO GENERIC SETTINGS SO THAT THEY ARE AVAILABLE ON ALL MACHINES
  options.roles.nginxHost = {
    enable = mkBoolOpt false "Enable NGINX";
    sslCertPath =
      mkOpt types.path config.luxnix.generic-settings.sslCertificatePath
        "Path to SSL certificate";
    sslKeyPath =
      mkOpt types.path config.luxnix.generic-settings.sslCertificateKeyPath
        "Path to SSL key";
    keycloak = {
      enable = mkBoolOpt false "Enable Keycloak routing";
    };
    nextcloud = {
      enable = mkBoolOpt false "Enable Nextcloud routing";
    };
    glm52 = {
      enable = mkBoolOpt false "Enable GLM-5.2 routing";
      domain = mkOpt types.str glm52Config.domain "Public domain for the GLM-5.2 endpoint";
      vpnIp = mkOpt types.str glm52Config.vpnIp "VPN IP of the GLM-5.2 llama.cpp server";
      port = mkOpt types.port glm52Config.port "Port of the GLM-5.2 llama.cpp server";
      extraLocationConfig = mkOpt types.lines "" "Additional nginx location config for the GLM-5.2 proxy";
      acme = {
        enable = mkBoolOpt true "Use the NixOS ACME module to issue and renew the GLM-5.2 TLS certificate";
        email =
          mkOpt (types.nullOr types.str) null
            "Optional Let's Encrypt contact email for the GLM-5.2 certificate";
      };
      oauth2 = {
        enable = mkBoolOpt true "Protect the public GLM-5.2 endpoint with oauth2-proxy";
        clientID = mkOpt types.str "glm-service" "Keycloak OIDC client ID for GLM-5.2";
        keyFile =
          mkOpt types.path "${nginxSecretsDir}/glm-oauth2-proxy.env"
            "Environment file containing OAUTH2_PROXY_CLIENT_SECRET and OAUTH2_PROXY_COOKIE_SECRET";
        clientSecretFile =
          mkOpt types.path "${nginxSecretsDir}/keycloak-glm-secret"
            "File containing the Keycloak OIDC client secret for GLM-5.2";
        cookieSecretFile =
          mkOpt types.path "${nginxSecretsDir}/glm-cookie-secret"
            "File containing the oauth2-proxy cookie secret for GLM-5.2";
        httpAddress = mkOpt types.str "http://127.0.0.1:4180" "Local oauth2-proxy listen address";
        issuerUrl =
          mkOpt types.str "https://${keycloakConfig.domain}/realms/master"
            "OIDC issuer URL for the Keycloak realm";
        redirectURL =
          mkOpt types.str "https://${glm52Config.domain}/oauth2/callback"
            "OAuth2 callback URL registered on the Keycloak client";
        emailDomains = mkOpt (types.listOf types.str) [ "*" ] "Allowed email domains for Keycloak users";
        allowedGroups =
          mkOpt (types.nullOr (types.listOf types.str)) null
            "Optional Keycloak groups allowed to access the GLM-5.2 vhost";
        allowedEmails =
          mkOpt (types.nullOr (types.listOf types.str)) null
            "Optional email addresses allowed to access the GLM-5.2 vhost";
        allowedEmailDomains =
          mkOpt (types.nullOr (types.listOf types.str)) null
            "Optional email domains allowed to access the GLM-5.2 vhost";
      };
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
          sslCertGroupName
          sensitiveServicesGroupName
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
      "d ${nginxStateDir} 0700 nginx nginx -"
      "d ${nginxSecretsDir} 0700 root root -"
    ];

    systemd.services.nginx-prepare-files = mkIf fileBackedTlsEnabled {
      description = "Deploy SSL certificate and key for NGINX";
      before = [ "nginx.service" ];
      requiredBy = [ "nginx.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = nginxSyncScript;
      };
    };

    systemd.services.nginx-sync-certificates = mkIf fileBackedTlsEnabled {
      description = "Synchronize SSL material for NGINX";
      after = [ "nginx-prepare-files.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = nginxSyncScript;
      };
    };

    systemd.paths.nginx-sync-certificates = mkIf fileBackedTlsEnabled {
      description = "Watch for SSL material changes";
      wantedBy = [ "multi-user.target" ];
      pathConfig = {
        PathChanged = [
          "${cfg.sslCertPath}"
          "${cfg.sslKeyPath}"
        ];
        Unit = "nginx-sync-certificates.service";
      };
    };

    systemd.timers.nginx-sync-certificates = mkIf fileBackedTlsEnabled {
      description = "Periodic SSL material synchronization";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "10m";
        OnUnitActiveSec = "6h";
        Unit = "nginx-sync-certificates.service";
      };
    };

    systemd.services.nginx = mkIf fileBackedTlsEnabled {
      wants = [ "nginx-prepare-files.service" ];
      after = [ "nginx-prepare-files.service" ];
    };

    systemd.services.glm-5-2-oauth2-proxy-env = mkIf (cfg.glm52.enable && cfg.glm52.oauth2.enable) {
      description = "Prepare oauth2-proxy secret environment for GLM-5.2";
      before = [ "oauth2-proxy.service" ];
      requiredBy = [ "oauth2-proxy.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = glm52Oauth2ProxyEnvScript;
      };
    };

    systemd.services.oauth2-proxy = mkIf (cfg.glm52.enable && cfg.glm52.oauth2.enable) {
      requires = [ "glm-5-2-oauth2-proxy-env.service" ];
      after = [ "glm-5-2-oauth2-proxy-env.service" ];
    };

    # make sure the user exists
    users.extraUsers."nginx" = {
      isSystemUser = true;
      group = "nginx";
      extraGroups = conf.extraGroups;
    };
    # make sure the group exists
    users.groups.nginx = { };

    # Allow default http and https ports
    networking.firewall.allowedTCPPorts = [
      80
      443
    ];

    security.acme = mkIf (cfg.glm52.enable && cfg.glm52.acme.enable) (
      {
        acceptTerms = true;
      }
      // optionalAttrs (cfg.glm52.acme.email != null) {
        defaults.email = cfg.glm52.acme.email;
      }
    );

    users.users.nginx.extraGroups = mkIf (cfg.glm52.enable && cfg.glm52.acme.enable) (mkAfter [ "acme" ]);

    services.oauth2-proxy = mkIf (cfg.glm52.enable && cfg.glm52.oauth2.enable) {
      enable = true;
      provider = "keycloak-oidc";
      clientID = cfg.glm52.oauth2.clientID;
      keyFile = cfg.glm52.oauth2.keyFile;
      oidcIssuerUrl = cfg.glm52.oauth2.issuerUrl;
      redirectURL = cfg.glm52.oauth2.redirectURL;
      httpAddress = cfg.glm52.oauth2.httpAddress;
      reverseProxy = true;
      setXauthrequest = true;
      passAccessToken = true;
      passBasicAuth = false;
      scope = "openid email profile";
      upstream = [ "http://${cfg.glm52.vpnIp}:${toString cfg.glm52.port}" ];
      email.domains = cfg.glm52.oauth2.emailDomains;
      cookie = {
        name = "_glm_oauth2_proxy";
        secure = true;
        httpOnly = true;
        expire = "8h0m0s";
        refresh = "1h0m0s";
      };
      nginx = {
        domain = cfg.glm52.domain;
        proxy = cfg.glm52.oauth2.httpAddress;
        virtualHosts."${cfg.glm52.domain}" = {
          allowed_groups = cfg.glm52.oauth2.allowedGroups;
          allowed_emails = cfg.glm52.oauth2.allowedEmails;
          allowed_email_domains = cfg.glm52.oauth2.allowedEmailDomains;
        };
      };
    };

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
          ${psqlMainConfig.domain} = {
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
          ${psqlTestConfig.domain} = {
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
          ${nextcloudConfig.domain} = {
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
        (mkIf cfg.glm52.enable {
          "${cfg.glm52.domain}" = {
            forceSSL = true;
            enableACME = cfg.glm52.acme.enable;
            sslCertificate = mkIf (!cfg.glm52.acme.enable) nginx_cert_path;
            sslCertificateKey = mkIf (!cfg.glm52.acme.enable) nginx_key_path;

            locations."/" = {
              proxyPass = "http://${cfg.glm52.vpnIp}:${toString cfg.glm52.port}";
              proxyWebsockets = true;
              extraConfig =
                all-extraConfig
                + ''
                  proxy_http_version 1.1;
                  proxy_buffering off;
                  proxy_request_buffering off;
                  proxy_read_timeout 3600s;
                  proxy_send_timeout 3600s;
                  client_max_body_size 100M;
                ''
                + cfg.glm52.extraLocationConfig;
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
