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
    
    environment.systemPackages = with pkgs; [
      vscode-fhs
      gparted exfatprogs ntfs3g
      easyrsa
    ];


  };
}
