{config, lib, pkgs, ...}: 

with lib; 
with lib.luxnix; let
  cfg = config.services.luxnix.traefik;
  dynCfgFile = "./${cfg.dynamicConfigFile}";
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
        # home = "/var/lib/traefik";
        # createHome = true;
      };
    };

    # 1) Create a dedicated directory and copy/symlink your cert/key files there.
    #    Adjust paths and permissions so that "traefik" can read them.
    
    systemd.tmpfiles.rules = [
      "d /etc/traefik 0750 traefik traefik -"
      "d /var/lib/traefik 0750 traefik traefik -"
      
      # log files
      "f /etc/traefik/traefik.log 0640 traefik traefik -"
      "f /etc/traefik/traefik-access.log 0640 traefik traefik -"
    ];
    systemd.services.traefik.restartIfChanged = true;
    systemd.services.traefik.wantedBy = [ "multi-user.target" ];



    environment.etc = {
      "traefik/ssl_cert.pem" = { 
        source = cfg.sslCertPath;
        user = "traefik";
        group = "traefik";
        mode = "0644";
      };

      "traefik/ssl_key.pem" = {
        source = cfg.sslKeyPath;
        user = "traefik";
        group = "traefik";
        mode = "0640";
      };

    };



    # 2) Define the Traefik service configuration
    services.traefik = {
      enable = true;
      package = pkgs.traefik;  # This should be v3.2 as per your channel
      group = "traefik";
      dataDir = "/var/lib/traefik";

      # The static (global) configuration for Traefik.
      # (Traefik uses “static” config for entrypoints, providers, etc.
      # and “dynamic” config for routers, services, and middlewares.)
      dynamicConfigFile = ./dynamic_conf.yaml;
      staticConfigOptions = {
        log = {
          level = "INFO";
          filePath = "/etc/traefik/traefik.log";
          format = "json";
        };
        metrics = {
          prometheus = {};
        };

        accessLog = {
          addInternals = true;
          filePath = "/etc/traefik/traefik-access.log";
          bufferingSize = 100;
          fields = {
            names = {
              StartUTC = "drop";
            };
          };
          filters = {
            statusCodes = [
              "204-299"
              "400-499"
              "500-599"
            ];
          };
        };
        api = {
          dashboard = true;
        };

        tracing = {};
        
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
            http = {
              tls = {};
            };
          };
        };

        tls = {
          stores = {
            default = {
              defaultCertificate = {
                certFile = "/etc/traefik/ssl_cert.pem";
                keyFile = "/etc/traefik/ssl_key.pem";
              };
            };
          };
          certificates = [
            {
              certFile = "/etc/traefik/ssl_cert.pem";
              keyFile = "/etc/traefik/ssl_key.pem";
            }
          ];
        };
      };
    };

    # (Optional) Ensure Traefik can read the certificate and key.
    # Here we “import” the files into NixOS’s /etc – adjust if you manage secrets differently.
    
    networking.firewall = {
      allowedTCPPorts = [ 80 443 ];
      allowedTCPPortRanges = mkIf cfg.dashboard [
        { from = 8080; to = 8080; }
      ];
    };
  };
}