{
  config,
  pkgs,
  lib,
  ...
}:
with lib; let
  cfg = config.programs.tuis;
in {
  options.programs.tuis = {
    enable = mkEnableOption "Enable TUI applications"; # CHANGEME?! Check what this is
  };

  config = mkIf cfg.enable {
    home.packages = with pkgs;
    with pkgs.luxnix; [
      s-tui
    ];
  };
}
