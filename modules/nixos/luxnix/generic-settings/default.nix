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

in {
  options.luxnix.generic-settings = {
    enable = mkEnableOption "Enable generic settings";

    systemStateVersion = mkOption {
      type = types.str;
      description = ''
        The system state version.
      '';
    };

    sensitiveServiceGroupName = mkOption {
      type = types.str;
      default = "sensitive-service-group";
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

    postgres = {
      defaultAuthentication = mkOption {
        type = types.str;
        default = ''
            #type database                  DBuser                      address                     auth-method         optional_ident_map
            local sameuser                  all                                                     peer                map=superuser_map
        '';
        description = ''
          The default ident map for postgres.
        '';
      };
      activeAuthentication = mkOption {
        type = types.str;
        default = cfg.postgres.defaultAuthentication;
        description = ''
          The active ident map for postgres.
        '';
      };

      defaultIdentMap = mkOption {
        type = types.str;
        default = ''
          # ArbitraryMapName systemUser DBUser
          superuser_map      root      postgres
          superuser_map      ${config.user.admin.name}     postgres
          superuser_map      postgres  postgres

          # Let other names login as themselves
          superuser_map      /^(.*)$   \1
      '';
      };

      activeIdentMap = mkOption {
        type = types.str;
        default = cfg.postgres.defaultIdentMap;
        description = ''
          The active ident map for postgres.
        '';
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
    users.groups = {
      "${cfg.sensitiveServiceGroupName}" = {
        gid = cfg.sensitiveServiceGID;
      };
    };

    users.mutableUsers = lib.mkDefault cfg.mutableUsers;
    system.stateVersion = cfg.systemStateVersion;
    networking.useDHCP = lib.mkDefault cfg.useDHCP;
  };


}