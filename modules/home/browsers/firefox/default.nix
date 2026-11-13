{
  lib,
  pkgs,
  config,
  ...
}:
with lib;
let
  cfg = config.browsers.firefox;
in
{
  options.browsers.firefox = {
    enable = mkEnableOption "enable firefox browser";
    certificateFiles = mkOption {
      type = types.listOf types.str;
      default = [ "/run/lx-annotate-ssl/lx-annotate-selfsigned.crt" ];
      description = ''
        Public certificate paths imported by Firefox at startup. The default
        trusts this machine's lxSsl certificate, published before Nginx starts.
        Use an empty list on machines without lxSsl, or supply the issuing CA
        for an explicitly configured Django TLS certificate. Runtime paths must
        be strings so evaluation does not copy them into the Nix store.
      '';
    };
  };

  config = mkIf cfg.enable {
    # home.file.".mozilla/firefox/default/chrome/firefox-gnome-theme".source = inputs.firefox-gnome-theme;

    xdg.mimeApps.defaultApplications = {
      "text/html" = [ "firefox.desktop" ];
      "text/xml" = [ "firefox.desktop" ];
      "x-scheme-handler/http" = [ "firefox.desktop" ];
      "x-scheme-handler/https" = [ "firefox.desktop" ];
    };

    programs.firefox = {
      enable = true;
      # home-manager 26.05 moved the default profile path under XDG_CONFIG_HOME.
      # Keep the classic ~/.mozilla/firefox location; no data move needed.
      policies = {
        Certificates = {
          ImportEnterpriseRoots = true;
          Install = cfg.certificateFiles;
        };
      };
      configPath = ".mozilla/firefox";
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
