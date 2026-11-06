{
  config,
  lib,
  ...
}:
let
  inherit (lib) mkDefault mkIf;
  inherit (lib.luxnix) mkBoolOpt;

  cfg = config.system.locale;
  genericSettings = config.luxnix.generic-settings;
  selectedLocale = if genericSettings.language == "english" then "en_US.UTF-8" else "de_DE.UTF-8";
in
{
  options.system.locale = {
    enable = mkBoolOpt false "Whether or not to manage locale settings.";
  };

  config = mkIf cfg.enable {
    environment.variables = {
      # LANG is used by most applications to decide on the language.
      LANG = selectedLocale;
      # LC_ALL forces all locale categories; use with caution since it overrides
      # more granular settings.
      LC_ALL = selectedLocale;
    };

    i18n = {
      defaultLocale = mkDefault selectedLocale;
      extraLocaleSettings = {
        LC_ADDRESS = selectedLocale;
        LC_IDENTIFICATION = "de_DE.UTF-8";
        LC_MEASUREMENT = "de_DE.UTF-8";
        LC_MONETARY = "de_DE.UTF-8";
        LC_NAME = "de_DE.UTF-8";
        LC_NUMERIC = "de_DE.UTF-8";
        LC_PAPER = "de_DE.UTF-8";
        LC_TELEPHONE = "de_DE.UTF-8";
        LC_TIME = "de_DE.UTF-8";
      };
    };
    time.timeZone = "Europe/Berlin";

    # Configure keymap in X11
    services.xserver = {
      xkb.layout = "de";
      xkb.variant = "";
    };
    # Configure console keymap
    console.keyMap = "de";
  };
}
