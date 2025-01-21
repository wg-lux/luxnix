{
  config,
  inputs,
  pkgs,
  lib,
  ...
}:

with lib;
with lib.luxnix; let
  cfg = config.luxnix.maintenance.autoUpdates;

in {
  options.luxnix.maintenance.autoUpdates = with types; {
    enable = mkBoolOpt false "Enable or disable the scheduled rebooting of the system";
    
    date = mkOption {
      type = with types; string;
      default = "08:46";
      description = "The time of day to perform the system upgrade";
    };

    flake = mkOption {
      type = with types; string;
      default = "github:wg-lux/luxnix"; #TODO Create Production Branch and use it here
      description = "The flake to upgrade";
    };

  };

  #TODO Documentation
  # systemctl status nixos-upgrade.timer

  # logs at
  # systemctl status nixos-upgrade.service 

  config = mkIf cfg.enable {
    system.autoUpgrade = {
      enable = cfg.enable;
      flake = cfg.flake;
      flags = [
        "-L"
      ];
      fixedRandomDelay = true;
      randomizedDelaySec = "30min";
      allowReboot = true;
    };
  };
  
}