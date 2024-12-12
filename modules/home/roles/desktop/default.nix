{
  pkgs,
  config,
  lib,
  ...
}:
with lib; let
  cfg = config.roles.desktop;

in {
  options.roles.desktop = {
    enable = mkEnableOption "Enable desktop suite";
  };

  config = mkIf cfg.enable {
    roles = {
      common.enable = true;
    };

    desktops = {
      plasma.enable = true;
    };

    services = {
      # spotify.enable = true;
    };
    
    # home.sessionVariables = {
    #   MOZ_ENABLE_WAYLAND = 1;
    #   QT_QPA_PLATFORM = "wayland;xcb";
    #   LIBSEAT_BACKEND = "logind";
    # };

    # TODO: move this to somewhere
    home.packages = with pkgs; [      
      mplayer
      brightnessctl
      xdg-utils
      clipse
      pamixer
      playerctl

      grimblast
      slurp
    ];
  };
}
