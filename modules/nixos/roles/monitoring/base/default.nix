{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.monitoring.base;
in {
  options.roles.monitoring.base = {
    enable = mkBoolOpt false "Enable base monitoring configuration";
  };

  config = mkIf cfg.enable {


  };
}
