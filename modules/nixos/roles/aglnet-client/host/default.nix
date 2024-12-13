{
  lib,
  pkgs,
  config,
  ...
}:
with lib; let
  cfg = config.roles.aglnet.host;

  defaultBackupNameservers = ["8.8.8.8" "1.1.1.1"];
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

  defaultUpdateResolvConf = true;

  updateResolvConfContent = ''
    #!/bin/bash
    # 
    # Parses DHCP options from openvpn to update resolv.conf
    # To use set as 'up' and 'down' script in your openvpn *.conf:
    # up /etc/openvpn/update-resolv-conf
    # down /etc/openvpn/update-resolv-conf
    #
    # Used snippets of resolvconf script by Thomas Hood and Chris Hanson.
    # Licensed under the GNU GPL.  See /usr/share/common-licenses/GPL. 
    # 
    # Example envs set from openvpn:
    #
    #     foreign_option_1='dhcp-option DNS 193.43.27.132'
    #     foreign_option_2='dhcp-option DNS 193.43.27.133'
    #     foreign_option_3='dhcp-option DOMAIN be.bnc.ch'
    #

    if [ ! -x /sbin/resolvconf ] ; then
        logger "[OpenVPN:update-resolve-conf] missing binary /sbin/resolvconf";
        exit 0;
    fi

    [ "$script_type" ] || exit 0
    [ "$dev" ] || exit 0

    split_into_parts()
    {
      part1="$1"
      part2="$2"
      part3="$3"
    }

    case "$script_type" in
      up)
      NMSRVRS=""
      SRCHS=""
      foreign_options=$(printf '%s\n' ${!foreign_option_*} | sort -t _ -k 3 -g)
      for optionvarname in ${foreign_options} ; do
        option="${!optionvarname}"
        echo "$option"
        split_into_parts $option
        if [ "$part1" = "dhcp-option" ] ; then
          if [ "$part2" = "DNS" ] ; then
            NMSRVRS="${NMSRVRS:+$NMSRVRS }$part3"
          elif [ "$part2" = "DOMAIN" ] ; then
            SRCHS="${SRCHS:+$SRCHS }$part3"
          fi
        fi
      done
      R=""
      [ "$SRCHS" ] && R="search $SRCHS
    "
      for NS in $NMSRVRS ; do
              R="${R}nameserver $NS
    "
      done
      echo -n "$R" | /sbin/resolvconf -a "${dev}.openvpn"
      ;;
      down)
      /sbin/resolvconf -d "${dev}.openvpn"
      ;;
    esac


  '';

in {
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
      default = true;
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

  };


  config = mkIf cfg.enable {
    environment = {
      systemPackages = with pkgs; [
        openvpn
      ];

      # etc = etc-files;

    };

    systemd.tmpfiles.rules = [
      "d /etc/openvpn 0750 admin users -"
    ];


    roles.base-server.enable=true;

    # Networking
    networking = {
      firewall = {
        "allowed${cfg.protocol}Ports" = [ cfg.port ];
      };
      nameservers = cfg.backupNameservers;
      # enableIPv4 = true;
      # forwarding = true;
    };

    # Create "/etc/openvpn/update-resolve-conf" file using environment.etc
    environment.etc."openvpn/update-resolve-conf".text = updateResolvConfContent;

    services.openvpn = let 
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

    # Secrets
    # sops.secrets = sops-secrets;

  };

}