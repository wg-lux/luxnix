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
    
    dates = mkOption {
      type = with types; str;
      default = "08:49";
      description = "The time of day to perform the system upgrade";
    };

    operation = mkOption {
      type = with types; str;
      default = "boot"; # alternatively: update
      description = "The operation to perform";
    };

    flake = mkOption {
      type = with types; str;
      default = "github:wg-lux/luxnix"; #TODO Create Production Branch and use it here
      description = "The flake to upgrade";
    };

  };

  #TODO Documentation
  #  unit-nixos-upgrade.timer
  # sudo systemctl status unit-script-nixos-upgrade-start
  # unit-script-nixos-upgrade-start
  # nixos-upgrade.timer
  # 
  #  unit-nixos-upgrade.service 

  config = mkIf cfg.enable {
    system.autoUpgrade = {
      enable = cfg.enable;
      flake = cfg.flake;
      flags = [
        "-L"
      ];
      dates = cfg.dates;
      operation = cfg.operation;
      fixedRandomDelay = false;
      # randomizedDelaySec = "30min";
      allowReboot = true;
    };
  };
  
}