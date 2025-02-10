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
      #FIXME make dynamic
      { "172.16.255.1" = [ "s-01" "s01.intern"]; } # s-01
      { "172.16.255.12" = [ "s-02" "s02.intern"]; } # s-02
      { "172.16.255.13" = [ "s-03" "s03.intern"]; } # s-03
      { "172.16.255.14" = [ "s-04" "s04.intern"]; } # s-04
      { "172.16.255.21" = [ "gs-01" "gs01.intern"]; } # gs-01
      { "172.16.255.22" = [ "gs-02" "gs02.intern"]; } # gs-01

      # gpu-clients 1-9 (gc-01 - gc-09; 172.16.255.101 to 109)
      { "172.16.255.101" = [ "gc-01" "gc01.intern" ]; }
      { "172.16.255.102" = [ "gc-02" "gc02.intern" ]; }
      { "172.16.255.103" = [ "gc-03" "gc03.intern" ]; }
      { "172.16.255.104" = [ "gc-04" "gc04.intern" ]; }
      { "172.16.255.105" = [ "gc-05" "gc05.intern" ]; }
      { "172.16.255.106" = [ "gc-06" "gc06.intern" ]; }
      { "172.16.255.107" = [ "gc-07" "gc07.intern" ]; }
      { "172.16.255.108" = [ "gc-08" "gc08.intern" ]; }
      { "172.16.255.109" = [ "gc-09" "gc09.intern" ]; }

      { "${cfg.keycloak.vpnIp}" = [ cfg.keycloak.domain cfg.keycloak.adminDomain ]; }
      { "${cfg.psqlMain.vpnIp}" = [ cfg.psqlMain.domain ]; }
      { "${cfg.psqlTest.vpnIp}" = [ cfg.psqlTest.domain ]; }
      { "${cfg.nginx.vpnIp}" = [ cfg.nginx.domain ]; }
    ];
  };

}
