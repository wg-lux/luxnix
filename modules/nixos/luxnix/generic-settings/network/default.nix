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
        default = 8443;
        description = ''
          The port.
        '';
      };
    };

    nextcloud = {
      vpnIp = mkOption {
        type = types.str;
        default = "172.16.255.x";
        description = ''
          The VPN IP.
        '';
      };
      port = mkOption {
        type = types.port;
        default = 8444;
        description = ''
          The port.
        '';
      };
    };

    psql-main = {
      vpnIp = mkOption {
        type = types.str;
        default = "172.16.255.x";
        description = ''
          The VPN IP.
        '';
      };
      port = mkOption {
        type = types.port;
        default = 5432;
        description = ''
          The port.
        '';
      };
    };

    psql-test = {
      vpnIp = mkOption {
        type = types.str;
        default = "172.16.255.x";
        description = ''
          The VPN IP.
        '';
      };
      port = mkOption {
        type = types.port;
        default = 5432;
        description = ''
          The port.
        '';
      };
    };



  };

  config = {
  };



}
