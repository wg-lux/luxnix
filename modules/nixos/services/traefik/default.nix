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
  };

  config = mkIf cfg.enable {

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
              forwardedHeaders.insecure = cfg.insecure;
            };
          };

          api = mkIf cfg.dashboard {
            dashboard = true;
            insecure = false;  # Changed to false for security
          };

          providers = {
            docker = {
              endpoint = "unix:///var/run/docker.sock";
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
            };
            routers = {
              dashboard = {
                rule = "Host(`${cfg.dashboardHost}`)";
                service = "api@internal";
                middlewares = ["ipwhitelist"];
                entryPoints = ["websecure"];
                tls = true;
              };
            };
          };

          # Configure TLS with existing wildcard certificate
          tls = {
            certificates = [
              {
                certFile = cfg.sslCertPath;
                keyFile = cfg.sslKeyPath;
              }
            ];
            options = {
              default = {
                minVersion = "VersionTLS12";
                sniStrict = true;  # Enable SNI since we're using proper certificates
              };
            };
          };
        }
        cfg.staticConfigOptions
      ];
    };

    # Modified hosts entry to use VPN IP instead of localhost
    networking.hosts = mkIf (hasSuffix "endo-reg.net" cfg.dashboardHost) {
      "${cfg.bindIP}" = [ cfg.dashboardHost ];
    };

    # Remove the self-signed certificate parts
    systemd.tmpfiles.rules = [
      "d /etc/traefik/config 0755 root root -"
    ];

    # Remove create-traefik-cert service since we're using existing certificates

    # Open required ports
    networking.firewall = {
      allowedTCPPorts = [ 80 443 ];
      allowedTCPPortRanges = mkIf cfg.dashboard [
        { from = 8080; to = 8080; }
      ];
    };

    # Enable Docker integration
    virtualisation.docker.enable = true;
  };
}