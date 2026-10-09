{
  lib,
  config,
  ...
}:

with lib;
with lib.luxnix;
let
  cfg = config.profiles.endoregGpuClient;
in
{
  options.profiles.endoregGpuClient = {
    enable = mkEnableOption "Enable reusable defaults for Endoreg GPU client hosts";
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

      endoreg-client.enable = mkDefault true;
      nextcloudClient.enable = mkDefault true;
    };

    luxnix.generic-settings.gpu = {
      autoDetect = mkDefault true;
      nvidia = {
        driver = mkDefault "production";
        enable = mkDefault true;
        prime = {
          enable = mkDefault true;
          onboardType = mkDefault "intel";
        };
      };
    };
  };
}
