{
  config,
  pkgs,
  lib,
  ...
}:
with lib; let
  cfg = config.luxnix.generic-settings;
in {
  options.luxnix.generic-settings = {
    enable = mkEnableOption "Enable generic luxnix home settings";

    configurationPath = mkOption {
      type = types.str;
      default = "luxnix-production";
      description = "The directory where the luxnix repository is located";
    };
  };

  config = mkIf cfg.enable {
    home.sessionVariables = {
      FLAKE = "/home/${config.luxnix.user.admin.name}/${cfg.configurationPath}";
    };
  };
}
