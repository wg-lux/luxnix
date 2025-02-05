{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.luxnix.generic-settings.network;


in {
  options.luxnix.generic-settings.network = {
    keycloak = {
      vpnIp = mkOption {
        type = types.str;
        default = "172.16.255.x";
        description = ''
          The VPN IP.
        '';
      };
      port = mkOption {
        type = types.port;
        default = 9080;
        description = ''
          The port.
        '';
      };
    };

  };

  config = {
  };



}
