{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.luxnix.generic-settings.network;

  mergeHosts = hostsList:
    builtins.foldl' (acc: hosts:
      let ip = builtins.head (builtins.attrNames hosts);
          names = hosts.${ip};
      in acc // { "${ip}" = (if builtins.hasAttr ip acc then acc.${ip} else []) ++ names; }
      ) {} hostsList;
      
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
      domain = mkOption {
        type = types.str;
        default = "keycloak.endo-reg.net";
        description = ''
          The domain.
        '';
      };
      adminDomain = mkOption {
        type = types.str;
        default = "keycloak-admin.endo-reg.net";
        description = ''
          The domain.
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
      domain = mkOption {
        type = types.str;
        default = "cloud.endo-reg.net";
        description = ''
          The domain.
        '';
      };
    };

    psqlMain = {
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
      domain = mkOption {
        type = types.str;
        default = "psql-main.endo-reg.net";
        description = ''
          The domain.
        '';
      };
    };

    psqlTest = {
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
      domain = mkOption {
        type = types.str;
        default = "psql-test.endo-reg.net";
        description = ''
          The domain.
        '';
      };
    };

    nginx = {
      vpnIp = mkOption {
        type = types.str;
        default = "172.16.255.x";
        description = ''
          The VPN IP.
        '';
      };
      port = mkOption {
        type = types.port;
        default = 443;
        description = ''
          The port.
        '';
      };
      domain = mkOption {
        type = types.str;
        default = "nginx.endo-reg.net";
        description = ''
          The domain.
        '';
      };
    };


  };


  config = {
    networking.hosts = mergeHosts [
      { "${cfg.keycloak.vpnIp}" = [ cfg.keycloak.domain cfg.keycloak.adminDomain ]; }
      { "${cfg.psqlMain.vpnIp}" = [ cfg.psqlMain.domain ]; }
      { "${cfg.psqlTest.vpnIp}" = [ cfg.psqlTest.domain ]; }
      { "${cfg.nginx.vpnIp}" = [ cfg.nginx.domain cfg.nextcloud.domain ]; }
    ];
  };

}
