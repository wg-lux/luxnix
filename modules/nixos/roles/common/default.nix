{
  lib,
  pkgs,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.common;
in {
  options.roles.common = {
    enable = mkEnableOption "Enable common configuration";
    packages = mkOption {
      type = with types; listOf package;
      default = with pkgs; [
        devenv
        parted
        cryptsetup
        lsof
        e2fsprogs
        nix-prefetch-scripts
      ];
      description = "List of additional packages to install.";
    };

  };

  config = mkIf cfg.enable {
    environment.systemPackages = cfg.packages;
    
    systemd.services.NetworkManager-wait-online.enable = lib.mkForce false;
    systemd.services.systemd-networkd-wait-online.enable = lib.mkForce false;
    security.rtkit.enable = lib.mkDefault true;
    programs.coolercontrol.enable = true;

    systemd.tmpfiles.rules = [
      "d /etc/user-passwords 0700 admin users -"
    ];

    roles.postgres.default.enable = lib.mkDefault true; 
    roles.custom-packages.enable = lib.mkDefault true;

    ########### MOVE TO MAINTENANCE BOOTMODE
    #TODO limit to vpn subnet
    services.ssh.enable = true;

    hardware = {
      networking.enable = true;
      graphics.enable = true;
    };

    nixpkgs.hostPlatform = config.luxnix.generic-settings.hostPlatform;
    
    cli.programs = {
      nh.enable = true;
      nix-ld.enable = true;
    };

    security = {
      sops.enable = true;
    };

    programs = {
      zsh.enable = true;
      command-not-found.enable = true;
    };

    services.virtualisation.podman.enable = true;

    system = {
      nix.enable = true;
      boot.enable = true;
      boot.secureBoot = false;
      locale.enable = true;
      boot.plymouth = true;
    };
  };
}
