{
  inputs,
  config,
  pkgs,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.video;
in {
  options.roles.video = with types; {
    enable = mkBoolOpt false "Whether or not to manage video editting and recording";
  };

  config = mkIf cfg.enable {
    xdg.configFile."obs-studio/themes".source = "${inputs.catppuccin-obs}/themes";

    programs.obs-studio = {
      enable = false;
    };

    home.packages = with pkgs; [
      # audacity
      # kdePackages.kdenlive
      # davinci-resolve-studio
    ];
  };
}
