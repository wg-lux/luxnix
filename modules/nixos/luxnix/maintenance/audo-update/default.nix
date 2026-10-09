{
  config,
  lib,
  ...
}:

with lib;
with lib.luxnix;
let
  cfg = config.luxnix.maintenance.autoUpdates;

in
{
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
      # TODO (maintenance owner): select a pinned production branch after the
      # release workflow publishes and verifies that branch.
      default = "github:wg-lux/luxnix";
      description = "The flake to upgrade";
    };

  };

  # TODO (maintenance owner): document timer inspection and rollback commands
  # in the module runbook before enabling unattended upgrades on production hosts.
  # sudo systemctl status nixos-upgrade.timer
  # sudo systemctl status nixos-upgrade.service

  config = mkIf cfg.enable {
    system.autoUpgrade = {
      inherit (cfg)
        enable
        flake
        dates
        operation
        ;
      flags = [
        "-L"
      ];
      fixedRandomDelay = true;
      randomizedDelaySec = "30min";
      allowReboot = true;
    };
  };

}
