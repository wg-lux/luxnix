{ lib
, pkgs
, config
, ...
}:
with lib; let
  cfg = config.roles.aglnet.host;

  defaultBackupNameservers = [ "8.8.8.8" "1.1.1.1" ];
  defaultPort = 1194;
  defaultProtocol = "TCP";
  defaultProtocolLc = "tcp";

  defaultDev = "tun";
  defaultDomain = "vpn.endo-reg.net";

  defaultSubnet = "172.16.255.0";
  defaultSubnetIntern = "255.255.255.0";
  defaultSubnetSuffix = "32";
  defaultKeepalive = "10 1200";
  defaultCipher = "AES-256-GCM";
  defaultVerbosity = "3";


  defaultCaPath = "/etc/openvpn/ca.pem";
  defaultTlsAuthPath = "/etc/openvpn/tls.pem";
  defaultServerCertPath = "/etc/openvpn/crt.crt";
  defaultServerKeyPath = "/etc/openvpn/key.key";
  defaultDhPath = "/etc/openvpn/dh.pem";

  defaultClientConfigDir = "/etc/openvpn/ccd";
  defaultTopology = "subnet";

  defaultAutostart = true;
  defaultRestartAfterSleep = true;
  defaultResolvRetry = "infinite";

  defaultPersistKey = true;
  defaultPersistTun = true;

  defaultClientToClient = true;

  defaultUpdateResolvConf = false;

  defaultLocalDomain = "endoreg.intern"; # Change default domain

in
{
  options.roles.aglnet.host = {
    enable = mkEnableOption "Enable aglnet-host openvpn configuration";

    networkName = mkOption {
      type = types.str;
      default = "aglnet";
      description = "The network name for the vpn";
    };

    mainDomain = mkOption {
      type = types.str;
      default = defaultDomain;
      description = "The main domain for the vpn";
    };

    backupNameservers = mkOption {
      type = types.listOf types.str;
      default = defaultBackupNameservers;
      description = "Backup nameservers for the VPN";
    };

    port = mkOption {
      type = types.int;
      default = defaultPort;
      description = "Port for the VPN";
    };

    protocol = mkOption {
      type = types.str;
      default = defaultProtocol;
      description = "Protocol for the VPN";
    };

    protocolLc = mkOption {
      type = types.str;
      default = defaultProtocolLc;
      description = "Lowercase protocol for the VPN";
    };

    restartAfterSleep = mkOption {
      type = types.bool;
      default = defaultRestartAfterSleep;
      description = "Restart VPN after sleep";
    };

    autoStart = mkOption {
      type = types.bool;
      default = defaultAutostart;
      description = "Autostart VPN on boot";
    };

    updateResolvConf = mkOption {
      type = types.bool;
      default = defaultUpdateResolvConf;
      description = "Update resolv.conf with VPN nameservers";
    };

    resolvRetry = mkOption {
      type = types.str;
      default = defaultResolvRetry;
      description = "Resolv retry for the VPN";
    };

    dev = mkOption {
      type = types.str;
      default = defaultDev;
      description = "Device for the VPN";
    };

    subnet = mkOption {
      type = types.str;
      default = defaultSubnet;
      description = "Subnet for the VPN";
    };

    subnetIntern = mkOption {
      type = types.str;
      default = defaultSubnetIntern;
      description = "Subnet intern for the VPN";
    };

    subnetSuffix = mkOption {
      type = types.str;
      default = defaultSubnetSuffix;
      description = "Subnet suffix for the VPN";
    };

    keepalive = mkOption {
      type = types.str;
      default = defaultKeepalive;
      description = "Keepalive for the VPN";
    };

    cipher = mkOption {
      type = types.str;
      default = defaultCipher;
      description = "Cipher for the VPN";
    };

    verbosity = mkOption {
      type = types.str;
      default = defaultVerbosity;
      description = "Verbosity for the VPN";
    };

    caPath = mkOption {
      type = types.str;
      default = defaultCaPath;
      description = "Path to CA certificate";
    };

    tlsAuthPath = mkOption {
      type = types.str;
      default = defaultTlsAuthPath;
      description = "Path to TLS auth key";
    };

    serverCertPath = mkOption {
      type = types.str;
      default = defaultServerCertPath;
      description = "Path to server certificate";
    };

    serverKeyPath = mkOption {
      type = types.str;
      default = defaultServerKeyPath;
      description = "Path to server key";
    };

    dhPath = mkOption {
      type = types.str;
      default = defaultDhPath;
      description = "Path to DH parameters";
    };

    clientConfigDir = mkOption {
      type = types.str;
      default = defaultClientConfigDir;
      description = "Path to client configuration directory";
    };

    topology = mkOption {
      type = types.str;
      default = defaultTopology;
      description = "Topology for the VPN";
    };

    persistKey = mkOption {
      type = types.bool;
      default = defaultPersistKey;
      description = "Persist key for the VPN";
    };

    persistTun = mkOption {
      type = types.bool;
      default = defaultPersistTun;
      description = "Persist tun for the VPN";
    };

    client-to-client = mkOption {
      type = types.bool;
      default = defaultClientToClient;
      description = "Client to client for the VPN";
    };

    localDomain = mkOption {
      type = types.str;
      default = defaultLocalDomain;
      description = "Local domain for VPN network";
    };

  };


  config = mkIf cfg.enable {
    environment = {
      systemPackages = with pkgs; [
        openvpn
      ];
    };

    systemd.tmpfiles.rules = [
      "d /etc/openvpn 0750 admin users -" #TODO Harden?
    ];




    # Networking
    networking = {
      firewall = {
        "allowed${cfg.protocol}Ports" = [ cfg.port ];
        interfaces = {
          "${cfg.dev}0" = {
            allowedUDPPorts = [ 53 ];
            allowedTCPPorts = [ 53 ];
          };
        };
      };
      nameservers = [ "172.16.255.1" ]; # Override system nameserver to ensure VPN DNS is used
      search = [ cfg.localDomain ]; # Add explicit DNS search domain
    };

    # Configure dnsmasq
    services.dnsmasq = {
      enable = true;
      settings = {
        # Only use upstream DNS for non-local domains
        server = cfg.backupNameservers;

        # Only handle .intern domain internally
        domain = cfg.localDomain;
        local = "/${cfg.localDomain}/";

        # Only listen on VPN interface
        interface = "${cfg.dev}0";
        bind-interfaces = true;
        listen-address = "172.16.255.1"; # VPN server IP

        # Don't modify non-local queries
        domain-needed = true;
        bogus-priv = true;
        no-resolv = false;
        no-poll = true;

        # Add static DNS entries (without TTL)
        address = [ ];

        # Don't read /etc/hosts
        no-hosts = true;

        # Explicitly set DNS order
        strict-order = true;

        # Log DNS queries for debugging
        log-queries = true;
      };
    };

    services.openvpn =
      let
        config = ''
          port ${toString cfg.port}
          proto ${cfg.protocolLc}
          dev ${cfg.dev}
          server ${cfg.subnet} ${cfg.subnetIntern}
        
          ${if cfg.persistKey then "persist-key" else ""}
          ${if cfg.persistTun then "persist-tun" else ""}

          keepalive ${cfg.keepalive}
          cipher ${cfg.cipher}
          push "route ${cfg.subnet} ${cfg.subnetIntern}"        
          verb ${cfg.verbosity}

          ca ${cfg.caPath}  
          tls-auth ${cfg.tlsAuthPath} 0
          cert ${cfg.serverCertPath}
          key ${cfg.serverKeyPath}
          dh ${cfg.dhPath}

          client-config-dir ${cfg.clientConfigDir}
          topology ${cfg.topology}

          ${if cfg.client-to-client then "client-to-client" else ""}

          # DNS and routing configuration
          push "route 172.16.255.0 255.255.255.0"  # Route all VPN subnet traffic
          push "route 172.16.255.1 255.255.255.255"  # Ensure DNS server is reachable
          push "route 172.16.255.12 255.255.255.255" # Nginx, keycloak
          push "dhcp-option DNS 172.16.255.1"
          push "dhcp-option DOMAIN ${cfg.localDomain}"
          push "dhcp-option DOMAIN-ROUTE ${cfg.localDomain}"
          push "dhcp-option DOMAIN-SEARCH ${cfg.localDomain}"  # Add search domain
        
        '';

      in
      {
        restartAfterSleep = cfg.restartAfterSleep;

        servers = {
          "${cfg.networkName}" = {
            config = config;
            autoStart = cfg.autoStart;
            updateResolvConf = cfg.updateResolvConf;
          };
        };
      };
  };

}
