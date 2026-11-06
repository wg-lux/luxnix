{
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.services.luxnix.redis;
in
{
  options.services.luxnix.redis = {
    enable = mkBoolOpt false "Enable redis";
  };

  config = mkIf cfg.enable {
    services = {
      redis.servers = {
        main = {
          enable = true;
          openFirewall = true;
          port = config.luxnix.generic-settings.network.redis.port;
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
                      address = "127.0.0.1:${toString config.services.redis.servers.main.port}";
                    }
                  ];
                };
              };
            };

            routers = {
              redis = {
                entryPoints = [ "redis" ];
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
