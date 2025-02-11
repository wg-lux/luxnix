{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.luxnix.generic-settings;
  hostname = config.networking.hostName;
  username = config.user.admin.name;


  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
  adminUserName = config.user.admin.name;
  keycloakEnabled = config.roles.keycloakHost.enable;
  keycloakUserName = config.roles.keycloakHost.dbUsername;


in {
  options.luxnix.generic-settings = {
    enable = mkEnableOption "Enable generic settings";

    systemStateVersion = mkOption {
      type = types.str;
      description = ''
        The system state version.
      '';
    };

    vpnIp = mkOption {
      type = types.str;
      default = "172.16.255.x";
      description = ''
        The VPN IP.
      '';
    };

    vpnSubnet = mkOption {
      type = types.str;
      default = "172.16.255.0/24";
      description = ''
        The VPN subnet.
      '';
    };

    adminVpnIp = mkOption {
      type = types.str;
      default = "172.16.255.106";
      description = ''
        The VPN IP of the admin.
      '';
    };

    traefikHostDomain = mkOption {
      type = types.str;
      default = "traefik.endoreg.local";
      description = ''
        The traefik dashboard host.
      '';
    };

    traefikHostIp = mkOption {
      type = types.str;
      default = "172.16.255.106";
      description = ''
        The traefik dashboard host.
      '';
    };

    secretDir = mkOption {
      type = types.path;
      default = "/etc/secrets";
      description = ''
        The directory where secrets are stored.
      '';
    };

    sensitiveServiceGroupName = mkOption {
      type = types.str;
      default = "sensitiveServices";  # changed from "sensitive-service-group"
      description = ''
        The name of the sensitive service group.
      '';
    };

    hostPlatform = mkOption {
      type = types.str;
      default = "x86_64-linux";
      description = "Default Host Platform";
    };

    sensitiveServiceGID = mkOption {
      type = types.int;
      default = 901;
      description = ''
        The GID of the sensitive service group.
      '';
    };

    mutableUsers = mkOption {
      type = types.bool;
      default = false;
      description = ''
        Allow users to be mutable.
      '';
    };

    useDHCP = mkOption {
      type = types.bool;
      default = true;
      description = ''
        Use DHCP for network configuration.
      '';
    };

    language = mkOption {
      type = types.enum [ "english" "german" ];
      default = "german";
      description = ''
        Choose system language (e.g. "english", "german").
      '';
    };

    postgres = {
      enable = lib.mkOption {
        type = types.bool;
        default = false;
        description = "Enable postgres configuration.";
      };

      remote = {
        admin = {
            enable = lib.mkOption {
              type = types.bool;
              default = false;
              description = "Enable remote admin.";
          };
          vpnIp = mkOption {
            type = types.str;
            default = config.luxnix.generic-settings.adminVpnIp;
            description = "The remote admin ip.";
          };
        };
      };

      extraAuthentication = mkOption {
        type = types.str;
        default = '''';
        description = ''
          The active authentication settings for postgres.
        '';
      };

      extraIdentMap = mkOption {
        type = types.str;
        default = '''';
      };

    };
  
    sslCertificateKeyPath = mkOption {
      type = types.path;
      default = "/home/${config.user.admin.name}/.ssl/endo-reg-net.key";
      description = ''
        Path to the ssl certificate key.
      '';
    };
    sslCertificatePath = mkOption {
      type = types.path;
      default = "/home/${config.user.admin.name}/.ssl/__endo-reg_net.pem";
      description = ''
        Path to the ssl certificate.
      '';
    };

    smtpUserFilePath = mkOption {
      type = types.path;
      default = "/etc/secrets/vault/smtp_user";
      description = ''
        Path to the smtp user file.
      '';
    };

    smtpPwdFilePath = mkOption {
      type = types.str;
      default = "/etc/secrets/vault/smtp_pwd";
      description = ''
        The smtp user file.
      '';
    };

    configurationPathRelative = mkOption {
      type = types.str;
      default = "lx-production";
      description = ''
        Relative path to the luxnix directory.
      '';
    };
    configurationPath = mkOption {
      type = types.path;
      default = "/home/${config.user.admin.name}/${cfg.configurationPathRelative}/";
      description = ''
        Path to the luxnix directory.
      '';
    };

    systemConfigurationPath = mkOption {
      type = types.path;
      default = "/home/${config.user.admin.name}/${cfg.configurationPathRelative}/systems/x86_64-linux/${hostname}";
      description = ''
        Path to the systems specif nixos configuration directory.
      '';
    };

    rootIdED25519 = mkOption {
      type = types.str;
      default = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M";
      description = ''
        The root
      '';
    };
  };

  config = {
    # Create Sensitive Service Group
    #TODO Migrate to groups
    users.groups = {
      "${cfg.sensitiveServiceGroupName}" = {
        gid = cfg.sensitiveServiceGID;
        name = sensitiveServiceGroupName;
        members = [ 
          adminUserName
        ] ++ ( if keycloakEnabled then [ keycloakUserName ] else [] );
      };
    };
    # Set PostGres Authentication & IdentMap
    roles.postgres.default.enable = lib.mkDefault cfg.postgres.enable;

    
    # TODO Add to System summary Log
    users.mutableUsers = lib.mkDefault cfg.mutableUsers;
    system.stateVersion = cfg.systemStateVersion;
    networking.useDHCP = lib.mkDefault cfg.useDHCP;
    # use tmpfile rule to create secret directory belonging to admin:users
    systemd.tmpfiles.rules = [
      "d ${cfg.secretDir} 0755 ${username} users"
    ];
  }
  // (if cfg.postgres.enable then {
    # pass extra auth and ident map to postgresql
    services.luxnix.postgresql.extraAuthentication = lib.mkDefault cfg.postgres.extraAuthentication;
    services.luxnix.postgresql.extraIdentMap = lib.mkDefault cfg.postgres.extraIdentMap;


  } else {});



}
