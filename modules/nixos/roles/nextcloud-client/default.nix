{ config, lib, pkgs, ... }:

with lib;
with lib.luxnix; let
  cfg = config.roles.nextcloudClient;

  conf = config.luxnix.generic-settings.network.nextcloud;



in
{
  options.roles.nextcloudClient = {
    enable = mkBoolOpt false "Enable Nextcloud Client Apps";
  };


  config = mkIf cfg.enable
    {
      environment.systemPackages = with pkgs; [
        nextcloud-client
        nextcloud-notify_push
        nextcloud-talk-desktop
      ];

    };
}
