{
  lib,
  pkgs,
  config,
  ...
}:
with lib; 
with lib.luxnix; let
  cfg = config.luxnix.hardware;
  
in {
  options.luxnix.hardware = {
    enable = mkEnableOption "Enable Default Hardware configuration";

  };


  config = mkIf cfg.enable {

  };
}
