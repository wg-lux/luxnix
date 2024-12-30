{
  lib,
  pkgs,
  config,
  ...
}:
with lib; 
with lib.luxnix; let
  cfg = config.luxnix.gpu-eval;
in {
  options.luxnix.gpu-eval = {
    enable = mkBoolOpt false "Enable Default GPU Evaluation configuration";
  };


  config = mkIf cfg.enable {
    programs.steam = {
      enable = true;
      remotePlay.openFirewall = true;
      dedicatedServer.openFirewall = true;
      gamescopeSession.enable = true;
    };

    xdg.portal.enable = true;
    xdg.portal.extraPortals = [ pkgs.xdg-desktop-portal-gtk ];
  };
}
