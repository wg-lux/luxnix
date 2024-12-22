{
  config,
  inputs,
  pkgs,
  lib,
  ...
}:

with lib;
with lib.luxnix; let
  cfg = config.luxnix.traefik-host;
  
in {
  options.luxnix.traefik-host = with types; {
    enable = mkBoolOpt false "Enable or disable the default traefik reverse proxy host configuration";
  };

  config = mkIf cfg.enable {
    networking.firewall.allowedTCPPorts = [ 8300 80 443 ];

    services.traefik = {
      enable = true;

      staticConfigOptions = {
        entryPoints = {
          web = {
            address = ":80";
            asDefault = true;
            http.redirections.entrypoint = {
              to = "websecure";
              scheme = "https";
            };
          };

          websecure = {
            address = ":443";
            asDefault = true;
            http.tls.certResolver = "letsencrypt";
          };
        };

        log = {
          level = "INFO";
          filePath = "${config.services.traefik.dataDir}/traefik.log";
          format = "json";
        };

        certificatesResolvers.letsencrypt.acme = {
          email = "postmaster@endo-reg.net";
          storage = "${config.services.traefik.dataDir}/acme.json";
          httpChallenge.entryPoint = "web";
        };

        api.dashboard = true;
        # Access the Traefik dashboard on <Traefik IP>:8080 of your server
        api.insecure = true;
      };

      dynamicConfigOptions = {
        http.routers = {};
        http.services = {};
      };
    };
  };
  
}