{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.luxnix.generic-settings.network;
  hostname = config.networking.hostName;
  
  # Add proper null handling for host config lookup
  ownNetConfig = cfg.hosts.${hostname} or {};
  
  # Add proper null handling for network-cluster
  ownNetworkCluster = ownNetConfig.network-cluster or null;

  mergeHosts = hostsList:
    builtins.foldl' (acc: hosts:
      let ip = builtins.head (builtins.attrNames hosts);
          names = hosts.${ip};
      in acc // { "${ip}" = (if builtins.hasAttr ip acc then acc.${ip} else []) ++ names; }
    ) {} hostsList;

  # Update generateHosts to handle null network-cluster values
  generateHosts = hosts:
    mapAttrs (hostName: hostConfig:
      let
        # Get cluster values with null handling
        hostCluster = hostConfig.network-cluster or null;
        myCluster = ownNetworkCluster;
        
        # Default to VPN IP if either cluster is null
        sameCluster = hostCluster != null && myCluster != null && hostCluster == myCluster;
        
        # Choose appropriate IP with fallbacks
        ip = if sameCluster && hostConfig.ip-local != null
             then hostConfig.ip-local
             else hostConfig.ip-vpn;
             
        # Default to empty list if domains is null
        domains = hostConfig.domains or ["localhost"];
      in { 
        "${ip}" = [ hostName ] ++ domains;
      }
    ) hosts;

  merged_hosts = mergeHosts (builtins.attrValues (generateHosts cfg.hosts));

in {
  options.luxnix.generic-settings.network = {#

    hosts = mkOption {
      type = types.attrsOf (types.submodule {
      options = {
        ip-local = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = ''
          Local IP address for hosts in the same network cluster.
        '';
        };
        ip-vpn = mkOption {
        type = types.str;
        default = "172.16.255.x";
        description = ''
          VPN IP address for hosts outside the local network cluster.
        '';
        };
        hostname = mkOption {
        type = types.str;
        default = "";
        description = ''
          Host name. Defaults to the attribute key if unset.
        '';
        };
        domains = mkOption {
        type = types.nullOr (types.listOf types.str);
        default = null;
        description = ''
          A list of alternative domains for the host.
        '';
        };
        syncthing-id = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = ''
          Optional Syncthing identifier.
        '';
        };
        network-cluster = mkOption {
        type = types.nullOr types.str;
        default = config.networking.hostName;
        description = ''
          Identifier for the network cluster the host belongs to.
        '';
        };
        
      };
      });
      default = {};
      description = ''
      Host configuration passed from Ansible inventory.
      Each host (<name>) can configure:
        - ip_local
        - ip_vpn
        - hostname
        - domains
        - syncthing_id
        - network_cluster
      '';
    };
    syncthing = {
      extraFlags = mkOption {
        type = types.listOf types.str;
        default = [];
        description = ''
          Extra flags for Syncthing.
        '';
      };
    };
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
    networking.hosts =  merged_hosts;
    services.luxnix.syncthing.extraFlags = lib.mkDefault cfg.syncthing.extraFlags;

  };

}
