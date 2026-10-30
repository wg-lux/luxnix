{
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.roles.base-server;
in
{
  options.roles.base-server = {
    enable = mkEnableOption "Enable base server configuration";
  };

  config = mkIf cfg.enable {

    roles = {
      common.enable = true;
      custom-packages.baseDevelopment = true;
    };

    services = {
      luxnix.avahi.enable = false;
    };
  };
}
