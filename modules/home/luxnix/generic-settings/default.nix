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

    language = mkOption {
      type = types.enum [ "english" "german" ];
      default = "german";
      description = ''
        Choose system language (e.g. "english", "german").
      '';
    };

    hostPlatform = mkOption {
      type = types.str;
      default = "x86_64-linux";
      description = ''
        The platform of the host system, e.g. "x86_64-linux".
      '';
    };

    configurationPath = mkOption {
      type = types.str;
      default = "lx-production";
      description = "The directory where the luxnix repository is located";
    };
  };

  config = mkIf cfg.enable {
    home.sessionVariables = {
      FLAKE = "/home/${config.luxnix.user.admin.name}/${cfg.configurationPath}";
    };
  };
}
