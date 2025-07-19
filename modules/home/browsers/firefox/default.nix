{
  inputs,
  lib,
  host,
  pkgs,
  config,
  ...
}:
with lib; let
  cfg = config.browsers.firefox;
in {
  options.browsers.firefox = {
    enable = mkEnableOption "enable firefox browser";
  };

  config = mkIf cfg.enable {
    # home.file.".mozilla/firefox/default/chrome/firefox-gnome-theme".source = inputs.firefox-gnome-theme;

    xdg.mimeApps.defaultApplications = {
      "text/html" = ["firefox.desktop"];
      "text/xml" = ["firefox.desktop"];
      "x-scheme-handler/http" = ["firefox.desktop"];
      "x-scheme-handler/https" = ["firefox.desktop"];
    };

    programs.firefox = {
      enable = true;
      profiles.default = {
        name = "Default";
        # extraConfig = ''
        #   ${builtins.readFile "${inputs.firefox-gnome-theme}/configuration/user.js"}
        # '';

        extensions.packages = with pkgs.nur.repos.rycee.firefox-addons; [
          # bitwarden
          ublock-origin
          # vimium
        ];

        settings = {
        };
      };
    };
  };
}
