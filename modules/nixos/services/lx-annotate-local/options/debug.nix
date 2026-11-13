{ lib, ... }:
let
  inherit (lib) mkOption types;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    debug = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = false;
            description = "Enable verbose debug output including sensitive file information. Should be disabled in production.";
          };
        };
      };
      default = { };
      description = "Debug configuration for lx-annotate-local.";
    };
  };
}
