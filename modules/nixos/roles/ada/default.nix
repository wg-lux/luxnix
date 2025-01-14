{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.ada;
in {
  options.roles.monitoring.center-client = {
    enable = mkBoolOpt false "Enable ADA configuration";
  };

  config = mkIf cfg.enable {  };
}
