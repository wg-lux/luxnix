{
  config,
  lib,
  pkgs,
  ...
}:

with lib;
with lib.luxnix;
let
  cfg = config.roles.nextcloudClient;

in
{
  options.roles.nextcloudClient = {
    enable = mkBoolOpt false "Enable Nextcloud Client Apps";
  };

  config = mkIf cfg.enable {
    luxnix.packages.roles.nextcloud-client = with pkgs; [
      nextcloud-client
      nextcloud-notify_push
      nextcloud-talk-desktop
    ];

  };
}
