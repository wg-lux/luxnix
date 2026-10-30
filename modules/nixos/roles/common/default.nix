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
        nix-prefetch-scripts
      ];
      description = "List of additional packages to install.";
    };
  };

  config = mkIf cfg.enable {
    luxnix.packages.roles.common = cfg.packages;

    systemd = {
      services.NetworkManager-wait-online.enable = lib.mkForce false;
      services.systemd-networkd-wait-online.enable = lib.mkForce false;
      tmpfiles.rules = [
        "d /etc/user-passwords 0700 admin users -"
      ];
    };

    roles = {
      postgres.default.enable = lib.mkDefault true;
      custom-packages.enable = lib.mkDefault true;
      managed-secrets.enable = lib.mkDefault true;
    };

    services = {
      luxnix.podman.enable = lib.mkDefault true;

      # TODO (common-role owner): restrict authorized SSH keys to the VPN subnet;
      # next action is to add the firewall/source-address option before moving
      # this access to maintenance boot mode.
      ssh = {
        enable = true;
        authorizedKeys = [
          # This list grants admin access; services.ssh controls the SSH service.
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
    };

    security = {
      rtkit.enable = lib.mkDefault true;
      sops.enable = true;
    };

    programs = {
      coolercontrol.enable = true;
      zsh.enable = true;
      command-not-found.enable = true;
    };

    system = {
      nix.enable = true;
      boot = {
        enable = true;
        secureBoot = mkDefault false;
        plymouth = true;
      };
      locale.enable = true;
    };
  };
}
