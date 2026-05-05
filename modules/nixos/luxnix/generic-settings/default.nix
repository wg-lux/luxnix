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

    nix = {
      enableOptimizations = mkBoolOpt true "Enable Nix build/caching optimizations";

      extraSubstituters = mkOption {
        type = types.listOf types.str;
        default = [      
          "https://nix-community.cachix.org"
          "https://cuda-maintainers.cachix.org"];
        description = "Extra binary caches (substituters) to use in addition to cache.nixos.org.";
      };

      maxJobs = mkOption {
        type = types.nullOr (types.either types.int types.str);
        default = "auto";
        description = "nix.settings.max-jobs (int or \"auto\").";
      };

      cores = mkOption {
        type = types.int;
        default = 0;
        description = "nix.settings.cores (0 = all cores).";
      };
    };


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
    endoregServiceGroupName = mkOption {
      type = types.str;
      default = "endoreg-service";
      description = ''
        The name of the endoreg service group.
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

    transferCaPath = mkOption {
      type = types.path;
      default = "/var/lib/lx-annotate/ssl/transfer_ca.crt";
      description = "Path to Transfer CA certificate used for mTLS/client certificate verification.";
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

    # GPU Configuration
    gpu = {
      autoDetect = mkBoolOpt true "Automatically detect and configure GPU";
      
      type = mkOption {
        type = types.enum ["nvidia" "amd" "intel" "none" "auto"];
        default = "auto";
        description = "Type of primary GPU (auto-detected if set to 'auto')";
      };
      
      nvidia = {
        enable = mkBoolOpt false "Enable Nvidia GPU support";
        driver = mkOption {
          type = types.enum ["stable" "beta" "production"];
          default = "beta";
          description = "Nvidia driver version to use";
        };
        
        prime = {
          enable = mkBoolOpt false "Enable Nvidia PRIME (hybrid graphics)";
          nvidiaBusId = mkOption {
            type = types.str;
            default = "PCI:01:00:0";
            description = "Bus ID of the Nvidia GPU";
          };
          onboardBusId = mkOption {
            type = types.str;
            default = "PCI:00:02:0";
            description = "Bus ID of the onboard GPU";
          };
          onboardType = mkOption {
            type = types.enum ["intel" "amd"];
            default = "intel";
            description = "Type of onboard GPU";
          };
        };
      };
      
      amd = {
        enable = mkBoolOpt false "Enable AMD GPU support";
        openSource = mkBoolOpt true "Use open source AMD drivers";
      };
      
      intel = {
        enable = mkBoolOpt false "Enable Intel GPU support";
        vaapi = mkBoolOpt true "Enable VA-API support";
      };
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
    services.luxnix.postgresql.extraAuthentication = lib.mkDefault cfg.postgres.extraAuthentication;
    services.luxnix.postgresql.extraIdentMap = lib.mkDefault cfg.postgres.extraIdentMap;
    
    # TODO Add to System summary Log
    users.mutableUsers = lib.mkDefault cfg.mutableUsers;
    system.stateVersion = cfg.systemStateVersion;
    networking.useDHCP = lib.mkDefault cfg.useDHCP;
    # Note: /etc/secrets directory is now managed by the managed-secrets role

    environment.systemPackages = with pkgs; [
      cacert
    ];

    nix.settings.ssl-cert-file = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";

    environment.variables = {
      SSL_CERT_FILE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";
      NIX_SSL_CERT_FILE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";
    };

    # GPU Configuration warnings
    warnings = 
      (optional (cfg.gpu.autoDetect && cfg.gpu.type != "auto")
        "GPU auto-detection is enabled but type is manually set - manual setting will take precedence")
      ++ (optional (cfg.gpu.nvidia.prime.enable && !cfg.gpu.nvidia.enable)
        "Nvidia PRIME is enabled but Nvidia GPU support is disabled");

    # GPU Configuration - Nvidia PRIME
    luxnix.nvidia-prime = mkIf (cfg.gpu.nvidia.enable && cfg.gpu.nvidia.prime.enable) {
      enable = true;
      nvidiaBusId = cfg.gpu.nvidia.prime.nvidiaBusId;
      onboardBusId = cfg.gpu.nvidia.prime.onboardBusId;
      onboardGpuType = cfg.gpu.nvidia.prime.onboardType;
      nvidiaDriver = cfg.gpu.nvidia.driver;
    };
    
    # GPU Configuration - Nvidia Default (non-PRIME)
    luxnix.nvidia-default = mkIf (cfg.gpu.nvidia.enable && !cfg.gpu.nvidia.prime.enable) {
      enable = true;
      nvidiaDriver = cfg.gpu.nvidia.driver;
    };
  };



}
