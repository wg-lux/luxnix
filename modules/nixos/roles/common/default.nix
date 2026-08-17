{
  lib,
  pkgs,
  config,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.roles.common;
in
{
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

    systemd = {
      services.NetworkManager-wait-online.enable = lib.mkForce false;
      services.systemd-networkd-wait-online.enable = lib.mkForce false;
      tmpfiles.rules = [
        "d /etc/user-passwords 0700 admin users -"
      ];
    };
    security.rtkit.enable = lib.mkDefault true;
    programs.coolercontrol.enable = true;

    roles = {
      postgres.default.enable = lib.mkDefault true;
      custom-packages.enable = lib.mkDefault true;
      managed-secrets.enable = lib.mkDefault true;
    };
    # services.luxnix.syncthing.enable = lib.mkDefault true;

    services = {
      luxnix.podman = {
        enable = lib.mkDefault true;
      };
      virtualisation.podman.enable = true;

      ########### MOVE TO MAINTENANCE BOOTMODE
      #TODO limit to vpn subnet
      ssh = {
        enable = true;
        authorizedKeys = [
          # just adds authorized keys for admin user, does not enable ssh!
          "${config.luxnix.generic-settings.rootIdED25519}"
        ];
      };
    };

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

    system = {
      nix.enable = true;
      boot = {
        enable = true;
        secureBoot = false;
        plymouth = true;
      };
      locale.enable = true;
    };
  };
}
