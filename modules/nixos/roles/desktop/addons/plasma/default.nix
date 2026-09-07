{
  config,
  lib,
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

    services = {
      desktopManager.plasma6.enable = true;
      displayManager = {
        defaultSession = "plasma"; # Correct session name for Plasma Wayland
        gdm = {
          enable = false;
          autoSuspend = false;
        };
        sddm = {
          enable = true;
          wayland.enable = true; # Forces the SDDM greeter to use Wayland
        };
      };
      xserver = {
        enable = true;
        # TODO (desktop-role owner): derive the keyboard layout from the locale
        # contract after generic-settings exports a dedicated XKB layout.
        xkb.layout = "de";
        xkb.variant = "";

      };
    };
  };
}
