{
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.cli.programs.nh;
in {
  options.cli.programs.nh = with types; {
    enable = mkBoolOpt false "Whether or not to enable nh (nix commandline helper).";
  };

  config = mkIf cfg.enable {
    programs.nh = {
      enable = true;
      clean.enable = true;
      clean.dates = "weekly";
      clean.extraArgs = "--keep-since 4d --keep 3"; # nh clean all --help
      flake = config.luxnix.generic-settings.configurationPath;
    };
  };
}
