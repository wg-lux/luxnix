{
  config,
  lib,
  ...
}:
#CHANGEME
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.netdata;
in {
  options.services.luxnix.netdata = {
    enable = mkBoolOpt false "Enable the netdata service";
  };

  config = mkIf cfg.enable {
    services = {
      netdata = {
        enable = true;
      };

      traefik = {
        dynamicConfigOptions = {
          http = {
            services = {
              netdata.loadBalancer.servers = [
                {
                  url = "http://localhost:19999";
                }
              ];
            };

            routers = {
              netdata = {
                entryPoints = ["websecure"];
                rule = "Host(`netdata.homelab.haseebmajid.dev`)";
                service = "netdata";
                tls.certResolver = "letsencrypt";
                middlewares = ["authentik"];
              };
            };
          };
        };
      };
    };
  };
}
