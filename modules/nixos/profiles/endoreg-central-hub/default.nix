{
  lib,
  config,
  ...
}:

with lib;
with lib.luxnix;
let
  cfg = config.profiles.endoregCentralHub;
in
{
  options.profiles.endoregCentralHub = {
    enable = mkEnableOption "Enable reusable defaults for Endoreg central hub hosts";
  };

  config = mkIf cfg.enable {
    roles = {
      aglnet.client.enable = mkDefault true;
      base-server.enable = mkDefault true;
      common.enable = mkDefault true;

      custom-packages = {
        enable = mkDefault true;
        cloud = mkDefault true;
      };

      endoreg-client = {
        enable = mkDefault true;
        repository.branch = mkDefault "container";
      };

      endoreg-db-central-01 = {
        enable = mkDefault true;

        api = {
          djangoDebug = mkDefault false;
          hostname = mkDefault "0.0.0.0";
          logLevel = mkDefault "INFO";
          port = mkDefault 8118;
          useHttps = mkDefault false;
        };

        database = {
          name = mkDefault "endoregDbCentral";
          sslMode = mkDefault "allow";
          user = mkDefault "endoregDbCentral";
        };

        service = {
          maxRequests = mkDefault 5000;
          workers = mkDefault 4;
        };
      };
    };
  };
}
