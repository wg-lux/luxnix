{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.roles.desktop.addons.plasma;
in
{
  options.roles.desktop.addons.plasma = with types; {
    enable = mkBoolOpt true "Enable or disable the plasma DE.";
  };

  config = mkIf cfg.enable {
    ###
    roles.custom-packages.kdePlasma = true;

    services.desktopManager.plasma6.enable = true;
    services.displayManager = {
      defaultSession = "plasma"; # Correct session name for Plasma Wayland
      sddm = {
        enable = true;
        wayland.enable = true; # Forces the SDDM greeter to use Wayland
      };
    };

    services.displayManager = {
      gdm = {
        enable = false;
        autoSuspend = false;
      };
    };

    services.xserver = {
      enable = true;
      xkb.layout = "de"; # TODO use locale via generic settings
      xkb.variant = "";

    };

  };
}
