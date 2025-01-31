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
    # Generate self-signed certificate for local development
    security.acme = {
      acceptTerms = true;
      defaults.email = "admin@endoreg.local";
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

          # Configure TLS
          tls = {
            certificates = [
              {
                certFile = "/var/lib/traefik/certificates/${cfg.dashboardHost}.crt";
                keyFile = "/var/lib/traefik/certificates/${cfg.dashboardHost}.key";
              }
            ];
            options = {
              default = {
                minVersion = "VersionTLS12";
                sniStrict = false;  # Allow non-SNI clients
              };
            };
          };
        }
        cfg.staticConfigOptions
      ];
    };

    # Modified hosts entry to use VPN IP instead of localhost
    networking.hosts = mkIf (hasSuffix "endoreg.local" cfg.dashboardHost) {
      "${cfg.bindIP}" = [ cfg.dashboardHost ];
    };

    # Generate self-signed certificate
    systemd.tmpfiles.rules = [
      "d /var/lib/traefik/certificates 0750 traefik traefik -"
      "d /etc/traefik/config 0755 root root -"
    ];

    # Create self-signed certificate using OpenSSL
    systemd.services.create-traefik-cert = {
      description = "Create self-signed certificate for Traefik";
      wantedBy = [ "traefik.service" ];
      before = [ "traefik.service" ];
      path = [ pkgs.openssl ];
      script = ''
        # Only create if it doesn't exist
        if [ ! -f "/var/lib/traefik/certificates/${cfg.dashboardHost}.crt" ]; then
          openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "/var/lib/traefik/certificates/${cfg.dashboardHost}.key" \
            -out "/var/lib/traefik/certificates/${cfg.dashboardHost}.crt" \
            -subj "/CN=${cfg.dashboardHost}/O=Endoreg Local/C=DE"
          chown traefik:traefik "/var/lib/traefik/certificates/${cfg.dashboardHost}.key"
          chown traefik:traefik "/var/lib/traefik/certificates/${cfg.dashboardHost}.crt"
          chmod 600 "/var/lib/traefik/certificates/${cfg.dashboardHost}.key"
        fi
      '';
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
    };

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