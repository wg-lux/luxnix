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
      default = "08:40";
      description = "The time of day to perform the system upgrade";
    };

    flake = mkOption {
      type = with types; string;
      default = "github:wg-lux/luxnix"; #TODO Create Production Branch and use it here
      description = "The flake to upgrade";
    };

  };

  config = mkIf cfg.enable {
    system.autoUpgrade = {
      enable = cfg.enable;
      fixedRandomDelay = true;
      randomizedDelaySec = "30min";
      allowReboot = true;
    };
  };
  
}