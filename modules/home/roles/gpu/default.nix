{
  config,
  pkgs,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.gpu;
in {
  options.roles.gpu = with types; {
    enable = mkBoolOpt false "Whether or not to manage gpu configuration";
  };

  config = mkIf cfg.enable {
    # programs.mangohud = {
    #   enable = true;
    #   enableSessionWide = true;
    #   settings = {
    #     cpu_load_change = true;
    #   };
    # };

    # home.packages = with pkgs; [
    #   lutris
    #   bottles
    # ];
  };
}