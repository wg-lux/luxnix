{
  options,
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.system.locale;
in {
  options.system.locale = with types; {
    enable = mkBoolOpt false "Whether or not to manage locale settings.";
  };

  config = mkIf cfg.enable {
    i18n = {
      defaultLocale = lib.mkDefault "de_DE.UTF-8";
      extraLocaleSettings = {
        LC_ADDRESS = "de_DE.UTF-8";
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
