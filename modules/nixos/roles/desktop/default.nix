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
      custom-packages.baseDevelopment = true;
      custom-packages.kdePlasma = true;
      custom-packages.office = true;
    };

    hardware = {
      audio.enable = true;
      bluetooth.enable = true;
    };
  };
}
