{ lib, ... }:
let
  inherit (lib) mkOption types;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    streamableMigration = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = true;
            description = "Expose the manual lx-annotate video streamable backfill systemd unit. The unit is not started by any target.";
          };
        };
      };
      default = { };
      description = "Settings for the manual streamable video backfill migration unit.";
    };
  };
}
