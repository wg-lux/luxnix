{
  config,
  lib,
  pkgs,
  ...
}:
#CHANGEME
with lib; 
with lib.luxnix; let
  cfg = config.services.luxnix.redis;
in {
  options.services.luxnix.redis = {
    enable = mkBoolOpt false "Enable redis";
  };

  config = mkIf cfg.enable {
    services = {
      redis.servers = {
        main = {
          enable = true;
          openFirewall = true;
          port = 6380;
          bind = "0.0.0.0";
          logLevel = "debug";
        };
      };

      traefik = {
        dynamicConfigOptions = {
          tcp = {
            services = {
              redis = {
                loadBalancer = {
                  servers = [
                    {
                      address = "127.0.0.1:6380";
                    }
                  ];
                };
              };
            };

            routers = {
              redis = {
                entryPoints = ["redis"];
                rule = "HostSNI(`*`)";
                service = "redis";
              };
            };
          };
        };
      };
    };
  };
}
