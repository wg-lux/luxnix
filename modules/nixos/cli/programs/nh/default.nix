{
  config,
  lib,
  ...
}:
let
  inherit (lib) mkIf;
  inherit (lib.luxnix) mkBoolOpt;

  cfg = config.cli.programs.nh;
  configurationPath = config.luxnix.generic-settings.configurationPath;
in
{
  options.cli.programs.nh = {
    enable = mkBoolOpt false "Whether or not to enable nh (nix commandline helper).";
  };

  config = mkIf cfg.enable {
    programs.nh = {
      enable = true;
      clean = {
        enable = true;
        dates = "weekly";
        extraArgs = "--keep-since 4d --keep 3"; # nh clean all --help
      };
      flake = configurationPath;
    };

    systemd.services.nh-clean.serviceConfig = {
      Nice = 19;
      IOSchedulingClass = "idle";
      CPUWeight = 10;
      IOWeight = 10;
      OOMScoreAdjust = 900;
    };
  };
}
