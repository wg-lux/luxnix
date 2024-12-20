{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.endoreg.boot-decryption-stick;
  hostname = config.networking.hostName;

in {
  options.luxnix.generic-settings = {
    enable = mkEnableOption "Enable generic settings";
  
    configurationPath = mkOption {
      type = types.path;
      default = "/home/${config.user.admin.name}/luxnix/";
      description = ''
        Path to the luxnix directory.
      '';
    };

    systemConfigurationPath = mkOption {
      type = types.path;
      default = "/home/${config.user.admin.name}/luxnix/systems/x86_64-linux/${hostname}";
      description = ''
        Path to the systems specif nixos configuration directory.
      '';
    };

    luxnixAdministrationPath = mkOption {
      type = types.path;
      default = "/home/${config.user.admin.name}/luxnix-administration";
      description = ''
        Path to the luxnix administration directory.
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


}