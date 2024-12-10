{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.monitoring.center-client;
in {
  options.roles.monitoring.center-client = {
    enable = mkBoolOpt false "Enable EndoReg Center Client monitoring configuration";
  };

  config = mkIf cfg.enable {


  };
}
