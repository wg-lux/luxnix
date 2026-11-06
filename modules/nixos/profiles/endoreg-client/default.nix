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

      # Inventory owns deployment policy; role options own reusable defaults.
      endoreg-client.enable = mkDefault true;
    };
  };
}
