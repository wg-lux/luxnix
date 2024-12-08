{
  options,
  config,
  pkgs,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.printing;
in {
  options.services.luxnix.printing = with types; {
    enable = mkBoolOpt false "Whether or not to configure printing support.";
  };

  config = mkIf cfg.enable {services.printing.enable = true;};
}
