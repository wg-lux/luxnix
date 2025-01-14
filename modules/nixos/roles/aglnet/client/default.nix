{
  lib,
  pkgs,
  config,
  ...
}:

with lib; let
  cfg = config.roles.aglnet.client;

  # defaultBackupNameservers = ["8.8.8.8" "1.1.1.1"];
  defaultPort = 1194;
  defaultProtocol = "TCP";
  defaultProtocolLc = "tcp";
  defaultDomain = "vpn.endo-reg.net";

  defaultUpdateResolvConf = false;

  defaultDev = "tun";

  defaultSubnet = "172.16.255.0";
  defaultSubnetIntern = "255.255.255.0";
  # defaultSubnetSuffix = "32";
  defaultKeepalive = "10 1200";
  defaultCipher = "AES-256-GCM";
  defaultVerbosity = "3";
  defaultNoBind = true;


  defaultCaPath = "/etc/openvpn/ca.pem";
  defaultTlsAuthPath = "/etc/openvpn/tls.pem";
  defaultServerCertPath = "/etc/openvpn/crt.crt";
  defaultServerKeyPath = "/etc/openvpn/key.key";
  # defaultDhPath = "/etc/identity/openvpn/dh.pem";

  # defaultClientConfigDir = "/etc/openvpn/ccd";
  # defaultTopology = "subnet";

  defaultAutostart = true;
  defaultRestartAfterSleep = true;
  defaultResolvRetry = "infinite";

  defaultPersistKey = true;
  defaultPersistTun = true;

  # defaultClientToClient = true;


in {
  options.roles.aglnet.client = {
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

    noBind = mkOption {
      type = types.bool;
      default = defaultNoBind;
      description = "Whether to add 'nobind' to config.";
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
  };


  config = mkIf cfg.enable {
    environment = {
      systemPackages = with pkgs; [
        openvpn
      ];
    };
#
    systemd.tmpfiles.rules = [
      "d /etc/openvpn 0750 admin users -"
    ];

    services.openvpn = let 
      config = ''
        client
        proto ${cfg.protocolLc}
        dev ${cfg.dev}
        remote ${cfg.mainDomain} ${toString cfg.port}
        
        resolv-retry ${cfg.resolvRetry}
        ${if cfg.noBind then "nobind" else ""}
        ${if cfg.persistKey then "persist-key" else ""}
        ${if cfg.persistTun then "persist-tun" else ""}

        ca ${cfg.caPath}  
        tls-auth ${cfg.tlsAuthPath} 1
        cert ${cfg.serverCertPath}
        key ${cfg.serverKeyPath}
        cipher ${cfg.cipher}
        
        route-nopull      
        route ${cfg.subnet} ${cfg.subnetIntern}

        remote-cert-tls server
        verb ${cfg.verbosity}      
      '';
    
    in {
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