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
environment.systemPackages = with pkgs; [
    kdePackages.xdg-desktop-portal-kde
    kdePackages.svgpart
    kdePackages.systemsettings
  ];

services.desktopManager.plasma6.enable = true;
  services.displayManager = {
    defaultSession = "plasmax11";
    sddm.enable = true;
    # sddm.wayland.enable = true;
  };

  services.xserver = {
    enable = true;
    xkb.layout = "de";
    xkb.variant = "";
    displayManager = {
      gdm= {
        enable = false;
        autoSuspend = false;
      };
    };
  };

####
#    services = {
#      xserver = {
#        enable = true;
#        displayManager.gdm.enable = true;
#        desktopManager.gnome = {
#          enable = true;
#          extraGSettingsOverridePackages = [
#            pkgs.nautilus-open-any-terminal
#          ];
#        };
#      };
#    };#

#    services.udev.packages = with pkgs; [gnome-settings-daemon];
#    programs.dconf.enable = true;
  };
}
