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
      staticConfigOptions = {
        global = {
          checkNewVersion = false;
          sendAnonymousUsage = false;
        };
        entryPoints = {
          web = {
            address = ":80";
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
            address = ":443";
          };
        };
        tls = {
          certificates = [{
            certFile = cfg.sslCertPath;
            keyFile = cfg.sslKeyPath;
          }];
        };
      };
      dynamicConfigOptions = {
        http = {
          routers = {
            # defaultRouter = { 
            #   entryPoints = [ "websecure" ];
            #   service = "basePage";
            #   rule = "Host(`endo-reg.net`)";
            #   tls = {};
            # };
            testPage = {
              rule = "Host(`test.endo-reg.net`)";
              service = "testPage";
              entryPoints = [ "websecure" ];
              # tls = {};
            };
          };

          services = {
            # basePage = {
            #   loadBalancer = {
            #     servers = [
            #       { url = "http://127.0.0.1:8080"; }
            #     ];
            #   };
            # };

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