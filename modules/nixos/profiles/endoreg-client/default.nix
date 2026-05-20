{
  lib,
  config,
  ...
}:

with lib;
with lib.luxnix;
let
  cfg = config.profiles.endoregClient;
in
{
  options.profiles.endoregClient = {
    enable = mkEnableOption "Enable reusable defaults for Endoreg client hosts";
  };

  config = mkIf cfg.enable {
    roles = {
      aglnet.client.enable = mkDefault true;
      common.enable = mkDefault true;

      custom-packages = {
        enable = mkDefault true;
        baseDevelopment = mkDefault true;
        cloud = mkDefault true;
      };

      endoreg-client = {
        enable = mkDefault true;
        centralNodes = mkDefault [ "s-04" ];
        dbApiLocal = mkDefault true;

        api = {
          djangoAllowedHosts = mkDefault [
            "localhost"
            "127.0.0.1"
            "172.16.255.106"
            "172.16.255.230"
          ];
          httpProtocol = mkDefault "https";
          language = mkDefault "en-us";
          logLevel = mkDefault "WARNING";
          maxRequestSize = mkDefault "50G";
          settingsProfile = mkDefault "prod";
        };

        repository.branch = mkDefault "container";
      };
    };
  };
}
