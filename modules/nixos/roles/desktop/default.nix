{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.desktop;
in {
  options.roles.desktop = {
    enable = mkEnableOption "Enable desktop configuration";
  };

  config = mkIf cfg.enable {


    boot.binfmt.emulatedSystems = [
      # "aarch64-linux"
    ];

    roles = {
      common.enable = true;

      desktop.addons = {
        plasma.enable = true;
      };
    };

    hardware = {
      audio.enable = true;
      bluetooth.enable = true;
      # zsa.enable = true;
    };

    services = {
      luxnix.avahi.enable = false;
      vpn.enable = false;
      virtualisation.podman.enable = false;
    };
    
    environment.systemPackages = with pkgs; [
    	vscode
      gparted exfatprogs ntfs3g
    ];

    system = {
      boot.plymouth = true;
    };

    cli.programs = {
      nh.enable = true;
      nix-ld.enable = true;
    };

    user = {
      name = "admin";
      initialPassword = "1";
    };
  };
}
