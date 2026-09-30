{ lib, ... }:
let
  inherit (lib) mkOption types;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    source = mkOption {
      type = types.submodule {
        options = {
          url = mkOption {
            type = types.str;
            default = "https://github.com/wg-lux/lx-annotate";
            description = "Git repository URL for the lx-annotate application.";
          };
          branch = mkOption {
            type = types.str;

            default = "test";
            description = "Git branch to checkout for lx-annotate.";
          };
          updateOnBoot = mkOption {
            type = types.bool;
            default = true;
            description = "Whether to update the lx-annotate repository on service start.";
          };
        };
      };
      default = { };
      description = "Repository configuration for lx-annotate.";
    };
  };
}
