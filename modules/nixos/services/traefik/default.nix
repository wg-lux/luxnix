{config, lib, pkgs, ...}: 

with lib; 
with lib.luxnix; let
  cfg = config.services.luxnix.traefik;
in {
  options.services.luxnix.traefik = {
    enable = mkBoolOpt false "Enable traefik";
    dashboard = mkBoolOpt true "Enable traefik dashboard";
    insecure = mkBoolOpt false "Allow insecure configurations";
    staticConfigOptions = mkOpt types.attrs {} "Additional static configuration options";
    dashboardHost = mkOpt types.str "traefik.endo-reg.net" "Hostname for the dashboard";
    allowedIPs = mkOpt (types.listOf types.str) ["127.0.0.1"] "IPs allowed to access the dashboard";
    bindIP = mkOpt types.str "0.0.0.0" "IP address to bind Traefik to";
    sslCertPath = mkOpt types.path config.luxnix.generic-settings.sslCertificatePath "Path to SSL certificate";
    sslKeyPath = mkOpt types.path config.luxnix.generic-settings.sslCertificateKeyPath "Path to SSL key";
    email = mkOpt types.str "admin@endoreg.intern" "Email address for Let's Encrypt";
    dnsProvider = mkOpt types.str "cloudflare" "DNS provider for ACME DNS challenge";
    dnsEnvVars = mkOpt types.attrs {} "Environment variables for DNS provider";
  };

  config = mkIf cfg.enable {

    users.groups.traefik = {};

    users.extraUsers = {
      traefik = {
        isSystemUser = true;
        group = "traefik";
        extraGroups = [ 
          "docker"
          "podman"
          "networkmanager"
          "sslCert"
          "sensitiveServices"
          ];
        home = "/var/lib/traefik";
        createHome = true;
      };
    };

    services.traefik = {
      enable = true;
      staticConfigOptions = mkMerge [
        {
          global = {
            checkNewVersion = false;
            sendAnonymousUsage = false;
          };

          entryPoints = {
            web = {
              address = ":80";
              http.redirections.entryPoint = {
                to = "websecure";
                scheme = "https";
              };
            };
            websecure = {
              address = ":443";
            };
          };

          # Simplified TLS configuration
          tls = {
            certificates = [{
              certFile = cfg.sslCertPath;
              keyFile = cfg.sslKeyPath;
            }];
          };

          api = mkIf cfg.dashboard {
            dashboard = true;
            insecure = true;  # Changed to false for security
          };

          providers = {
            docker = {
              endpoint = "unix:///var/run/podman/podman.sock"; 
              exposedByDefault = false;
              watch = true;
            };
            file = {
              directory = "/etc/traefik/config";
              watch = true;
            };
          };

          http = {
            middlewares = {
              ipwhitelist = {
                ipWhiteList = {
                  sourceRange = cfg.allowedIPs;
                };
              };
              keycloak-headers = {
                headers = {
                  customRequestHeaders = {
                    "X-Forwarded-Proto" = "https";
                    "X-Forwarded-Host" = "keycloak.endo-reg.net";
                    "X-Forwarded-For" = "true";
                    "X-Real-IP" = "true";
                  };
                };
              };
              keycloak_admin_ip_whitelist = {
                ipWhiteList = {
                  sourceRange = cfg.allowedIPs;
                };
              };
            };
            routers = {
              dashboard = {
                rule = "Host(`${cfg.dashboardHost}`)";
                service = "api@internal";
                middlewares = ["ipwhitelist"];
                entryPoints = ["websecure"];
                tls = false;
              };
              keycloak = {
                rule = "Host(`keycloak.endo-reg.net`)";
                service = "keycloak";
                entryPoints = ["websecure"];
                middlewares = ["keycloak-headers"];
                tls = {};
              };
              keycloak_admin = {
                rule = "Host(`keycloak-admin.endo-reg.net`)";
                service = "keycloak";
                middlewares = ["keycloak_admin_ip_whitelist"];
                entryPoints = ["websecure"];
                tls = {};
              };
            };
            services = {
              keycloak = {
                loadBalancer = {
                  servers = [
                    { url = "http://172.16.255.3:9080"; }  # Note the semicolon here
                  ];
                  passHostHeader = true;
                };
              };
            };
          };

        }
        cfg.staticConfigOptions
      ];

    };
    systemd.tmpfiles.rules = [
      "d /etc/traefik/config 0755 root root -"
    ];

    # Open required ports
    networking.firewall = {
      allowedTCPPorts = [ 80 443 ];
      allowedTCPPortRanges = mkIf cfg.dashboard [
        { from = 8080; to = 8080; }
      ];
    };


  };
}