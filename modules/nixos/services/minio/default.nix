{
  config,
  lib,
  ...
}:
# CHANGEME SETUP MINIO https://min.io/
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.minio;
in {
  options.services.luxnix.minio = {
    enable = mkBoolOpt false "Enable the minio";
  };

  config = mkIf cfg.enable {
    users.users.minio.extraGroups = ["media"];

    services = {
      minio = {
        enable = true;
        listenAddress = ":9055";
        consoleAddress = ":9056";
        dataDir = ["/mnt/share/minio"];
      };

      traefik = {
        dynamicConfigOptions = {
          http = {
            services = {
              minio.loadBalancer.servers = [
                {
                  url = "http://localhost:9056";
                }
              ];
            };

            routers = {
              minio = {
                entryPoints = ["websecure"];
                rule = "Host(`minio.homelab.haseebmajid.dev`)";
                service = "minio";
                tls.certResolver = "letsencrypt";
              };
            };
          };
        };
      };
    };
  };
}
