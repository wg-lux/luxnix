{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.monitoring.server;
in {
  options.roles.monitoring.server = {
    enable = mkBoolOpt false "Enable server monitoring configuration";
  };

  config = mkIf cfg.enable {
    

  };
}
