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

    # 1) Create a dedicated directory and copy/symlink your cert/key files there.
    #    Adjust paths and permissions so that "traefik" can read them.
    environment.etc = {
      "traefik/ssl_cert.pem".source = cfg.sslCertPath;
      "traefik/ssl_cert.pem".user = "traefik";
      "traefik/ssl_cert.pem".group = "traefik";
      "traefik/ssl_cert.pem".mode = "0644";

      "traefik/ssl_key.pem".source = cfg.sslKeyPath;
      "traefik/ssl_key.pem".user = "traefik";
      "traefik/ssl_key.pem".group = "traefik";
      "traefik/ssl_key.pem".mode = "0640";
    };

    # 2) Define the Traefik service configuration
    services.traefik = {
      enable = true;
      staticConfigOptions = {
        global = {
          checkNewVersion = false;
          sendAnonymousUsage = false;
        };

        entryPoints = {
          web = {
            address = "0.0.0.0:80";
            http.redirections.entryPoint = {
              to = "websecure";
              scheme = "https";
              permanent = true;
            };
          };
          websecure = {
            address = "0.0.0.0:443";
            http.tls = {
              domains = [
                {
                  main = "endo-reg.net";
                  sans = [ "*.endo-reg.net" ];
                }
              ];
            };
          };
        };

        tls = {
          stores = {
            default = {
              defaultCertificate = {
                # 3) Point to the new paths in /etc/traefik/
                certFile = "/etc/traefik/ssl_cert.pem";
                keyFile  = "/etc/traefik/ssl_key.pem";
              };
            };
          };

          certificates = [
            {
              certFile = "/etc/traefik/ssl_cert.pem";
              keyFile  = "/etc/traefik/ssl_key.pem";
            }
          ];
        };
      };

      dynamicConfigOptions = {
        http = {
          routers = {
            testPage = {
              rule = "Host(`test.endo-reg.net`)";
              service = "testPage";
              entryPoints = [ "websecure" ];
              tls = {};
            };
          };

          services = {
            testPage = {
              loadBalancer = {
                servers = [
                  { url = "http://172.16.255.12:8081"; }
                ];
              };
            };
          };
        };
      };
    };

    # 3) (Optional) Firewall rules & any tmpfiles if needed
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