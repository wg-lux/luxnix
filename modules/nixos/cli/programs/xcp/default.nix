{
  lib,
  pkgs,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.cli.programs.xcp;
in {
  options.cli.programs.xcp = with types; {
    enable = mkBoolOpt true "Whether or not to enable xcp";
  };

  config = mkIf cfg.enable {
    environment.systemPackages = with pkgs; [
      xcp
    ];
  };
}
