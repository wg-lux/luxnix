{
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.roles.base-server;
in
{
  options.roles.base-server = {
    enable = mkEnableOption "Enable base desktop server configuration";
  };

  config = mkIf cfg.enable {

    services.ssh = {
      enable = true;
      authorizedKeys = [
        "${config.luxnix.generic-settings.rootIdED25519}"
      ];
    };

    boot.binfmt.emulatedSystems = [
      # "aarch64-linux"
    ];

    roles = {
      desktop.enable = true;
      custom-packages.baseDevelopment = true;
    };

    services = {
      luxnix.avahi.enable = false;
      virtualisation.podman.enable = lib.mkDefault true;
    };

  };
}
