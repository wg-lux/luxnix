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
    keycloak = {
      enable = mkOption {
        type = types.bool;
        default = false;
        description = "Enable Keycloak routing";
      };
      domain = mkOpt types.str "keycloak.endo-reg.net" "Keycloak domain";
      port = mkOpt types.port 9080 "Keycloak HTTP port";
    };
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
              asDefault = true;
              http.redirections.entryPoint = {
                to = "websecure";
                scheme = "https";
              };
            };
            websecure = {
              address = ":443";
              asDefault = true;
            };
          };

          # Simplified TLS configuration
          tls = {
            certificates = [{
              certFile = cfg.sslCertPath;
              keyFile = cfg.sslKeyPath;
              domains = [
                {
                  main = "endo-reg.net";
                  sans = [ "*.endo-reg.net" ];
                }
              ];
            }];
          };

          log = {
            level = "INFO";
            filePath = "${config.services.traefik.dataDir}/traefik.log";
            format = "json";
          };

          api = mkIf cfg.dashboard {
            dashboard = true;
            insecure = false;
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

          http = mkIf cfg.keycloak.enable {
            routers = {
              keycloak = {
                rule = "Host(`${cfg.keycloak.domain}`)";
                service = "keycloak";
                entryPoints = [ "websecure" ];
                tls = {};
              };
            };
            services = {
              keycloak = {
                loadBalancer = {
                  servers = [
                    { url = "http://127.0.0.1:${toString cfg.keycloak.port}"; }
                  ];
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

    networking.firewall = {
      allowedTCPPorts = [ 80 443 ];
      allowedTCPPortRanges = mkIf cfg.dashboard [
        { from = 8080; to = 8080; }
      ];
    };


  };
}