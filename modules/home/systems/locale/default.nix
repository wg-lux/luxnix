{
  config,
  pkgs,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.system.locale;
in {
  options.system.locale = with types; {
    enable = mkBoolOpt false "Whether or not to manage nix configuration";
  };

  config = mkIf cfg.enable {
    home.sessionVariables = {
      # This ensures that every program started in your session, including Plasma,
      # sees the correct locale.
      LANG = (
        if config.luxnix.generic-settings.language == "english" 
        then "en_US.UTF-8" 
        else "de_DE.UTF-8"
      );
      LC_ALL = (
        if config.luxnix.generic-settings.language == "english" 
        then "en_US.UTF-8" 
        else "de_DE.UTF-8"
      );
    };
  };
}
