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

      # Inventory owns deployment policy; role options own reusable defaults.
      endoreg-client.enable = mkDefault true;
    };

    services.luxnix.lxAnnotateLocal = {
      hub.enable = mkDefault true;
      runtime.deploymentRole = mkDefault "central_hub";
    };
  };
}
