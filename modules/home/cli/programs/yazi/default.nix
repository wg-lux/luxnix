{
  pkgs,
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.cli.programs.yazi;
in
{
  options.cli.programs.yazi = with types; {
    enable = mkBoolOpt false "Whether or not to enable yazi";
  };

  config = mkIf cfg.enable {
    programs.yazi = {
      enable = true;
      enableFishIntegration = true;
      # home-manager 26.05 changed the default from "yy" to "y"; keep "yy".
      shellWrapperName = "yy";
    };

    home.packages = with pkgs; [
      imagemagick
      ffmpegthumbnailer
      fontpreview
      unar
      poppler
      unar
    ];
  };
}
