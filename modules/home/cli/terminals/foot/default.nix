{
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.cli.terminals.foot;
in {
  options.cli.terminals.foot = with types; {
    enable = mkBoolOpt false "enable foot terminal emulator";
  };

  config = mkIf cfg.enable {
    programs.foot = {
      enable = true;

      settings = {
        main = {
          # term = "foot";
          shell = "zsh";
          pad = "15x15";
          selection-target = "clipboard";
        };

        scrollback = {
          lines = 10000;
        };
      };
    };
  };
}
