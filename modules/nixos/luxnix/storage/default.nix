{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.luxnix.storage;
  hostname = config.networking.hostName;
  username = config.user.admin.name;

  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
  adminUserName = config.user.admin.name;
  endoregServiceUserName = config.user.endoreg-service-user.name;

in
{

  options.luxnix.storage = {
    enable = mkEnableOption "Enable Storage related settings for LuxNix systems";

  };

  config = mkIf cfg.enable (

    let
      endoregServiceUserName = config.user.endoreg-service-user.name;
    in
    {
      # add package smartmontools
      environment.systemPackages = with pkgs; [
        smartmontools
      ];

    }
  );
}
