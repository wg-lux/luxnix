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
    enable = mkBoolOpt false "Stage a reviewed revision for a separately authorized reboot";

    dates = mkOption {
      type = with types; str;
      default = "08:49";
      description = "The time of day to perform the system upgrade";
    };

    operation = mkOption {
      type = str;
      default = "boot";
      description = "Stage the reviewed system without live activation";
    };

    flake = mkOption {
      type = with types; str;
      default = "";
      description = "Reviewed github:wg-lux/luxnix/<full commit SHA> flake";
    };

  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion = builtins.match "github:wg-lux/luxnix/[0-9a-f]{40}" cfg.flake != null;
        message = "Scheduled upgrades require an explicitly reviewed full LuxNix commit SHA.";
      }
      {
        assertion = cfg.operation == "boot";
        message = "Scheduled upgrades may only stage boot; activation requires operator review.";
      }
    ];
    system.autoUpgrade = {
      inherit (cfg)
        enable
        flake
        dates
        operation
        ;
      flags = [
        "-L"
        "--no-update-lock-file"
      ];
      fixedRandomDelay = true;
      randomizedDelaySec = "30min";
      allowReboot = false;
    };
  };

}
