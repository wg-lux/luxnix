{
  config,
  lib,
  pkgs,
  ...
}:
let
  inherit (lib) mkIf;
  inherit (lib.luxnix) mkBoolOpt;
  cfg = config.system.boot;
in
{
  options.system.boot = {
    enable = mkBoolOpt false "Whether or not to enable booting.";
    plymouth = mkBoolOpt false "Whether or not to enable plymouth boot splash.";
    secureBoot = mkBoolOpt false "Whether or not to enable secure boot.";
    spaceManagement = mkBoolOpt true "Whether or not to enable boot space management and monitoring.";
  };

  config = mkIf cfg.enable {

    environment.systemPackages =
      with pkgs;
      [
        efibootmgr
        efitools
        efivar
        fwupd
      ]
      ++ lib.optionals cfg.secureBoot [ sbctl ];

    boot = {
      kernel.sysctl = {
        "net.core.rmem_max" = config.luxnix.generic-settings.linux.rmemMax;
        "net.core.wmem_max" = config.luxnix.generic-settings.linux.wmemMax;
      };

      kernelParams = lib.optionals cfg.plymouth [
        "quiet"
        "splash"
        "loglevel=3"
        "udev.log_level=0"
      ];
      # initrd.verbose = lib.optionals cfg.plymouth false;
      # consoleLogLevel = lib.optionals cfg.plymouth 0;
      initrd.systemd.enable = true;

      # lanzaboote = mkIf cfg.secureBoot {
      #   enable = true;
      #   pkiBundle = "/etc/secureboot";
      # };

      loader = {
        efi = {
          canTouchEfiVariables = true;
        };

        systemd-boot = {
          enable = !cfg.secureBoot;
          configurationLimit = if cfg.spaceManagement then 5 else 20;
          editor = false;
        };
      };

      plymouth = {
        enable = cfg.plymouth;
      };
    };

    # Boot space management configuration
    nix = mkIf cfg.spaceManagement {
      #gc = {
      #  automatic = true;
      # dates = "weekly";
      #  options = "--delete-older-than 30d";
      #  persistent = true;
      #};
      settings.auto-optimise-store = true;
    };

    # services.fwupd.enable = true;
  };
}
