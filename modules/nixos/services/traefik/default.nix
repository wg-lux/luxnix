{config, lib, ...}: 

with lib; 
with lib.luxnix; let
  cfg = config.services.luxnix.traefik;
in {
  options.services.luxnix.traefik = {
    enable = mkBoolOpt false "Enable traefik";
    dashboard = mkBoolOpt true "Enable traefik dashboard";
    insecure = mkBoolOpt false "Allow insecure configurations";
    staticConfigOptions = mkOpt types.attrs {} "Additional static configuration options";
    dashboardHost = mkOpt types.str "traefik.endoreg.local" "Hostname for the dashboard";
    allowedIPs = mkOpt (types.listOf types.str) ["127.0.0.1"] "IPs allowed to access the dashboard";
    externalCertResolver = mkOpt types.str "" "Name of the certificate resolver for external domains";
    bindIP = mkOpt types.str "0.0.0.0" "IP address to bind Traefik to";
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
              address = "${cfg.bindIP}:80";
              forwardedHeaders.insecure = cfg.insecure;
              http = {
                redirections = {
                  entryPoint = {
                    to = "websecure";
                    scheme = "https";
                  };
                };
              };
            };
            websecure = {
              address = "${cfg.bindIP}:443";
              forwardedHeaders.insecure = cfg.insecure;
            };
          };

          api = mkIf cfg.dashboard {
            dashboard = true;
            insecure = cfg.insecure;
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
        }
        cfg.staticConfigOptions
      ];
    };

    # Add dashboard hostname to /etc/hosts if it's the internal domain
    networking.hosts = mkIf (hasSuffix "endoreg.local" cfg.dashboardHost) {
      "127.0.0.1" = [ cfg.dashboardHost ];
    };

    # Create config directory for file provider
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

    # Enable Docker integration
    virtualisation.docker.enable = true;
  };
}