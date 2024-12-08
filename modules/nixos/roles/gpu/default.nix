{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.gpu;
in {
  options.roles.gpu = with types; {
    enable = mkBoolOpt false "Enable the gpu suite";
  };

  config = mkIf cfg.enable {
    hardware = {
      graphics = {
        enable = true;
        extraPackages = with pkgs; [
          mesa
        ];
      };
    };


    environment.systemPackages = with pkgs; [
    ];
  };
}
