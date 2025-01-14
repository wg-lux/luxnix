{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.desktop.addons.plasma;
in {
  options.roles.desktop.addons.plasma = with types; {
    enable = mkBoolOpt true "Enable or disable the plasma DE.";
  };

  config = mkIf cfg.enable {
###   
  roles.custom-packages.kdePlasma = true;

  services.desktopManager.plasma6.enable = true;
  services.displayManager = {
    defaultSession = "plasmax11";
    sddm.enable = true;
  };

  services.xserver = {
    enable = true;
    xkb.layout = "de"; # TODO use locale via generic settings
    xkb.variant = "";
    displayManager = {
      gdm= {
        enable = false;
        autoSuspend = false;
      };
    };
  };

  };
}
