{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.monitoring.dev-client;
in {
  options.roles.monitoring.dev-client = {
    enable = mkBoolOpt false "Enable Dev Client monitoring configuration";
  };

  config = mkIf cfg.enable {


  };
}
