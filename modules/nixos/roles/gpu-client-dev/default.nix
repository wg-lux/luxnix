{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.gpu-client-dev;
in {
  options.roles.gpu-client-dev = {
    enable = mkBoolOpt false ''
      Enable desktop configuration for gpu development clients.
      Enables roles:
      - desktop
      - aglnet.client
    '';
  };

  config = mkIf cfg.enable {

    services.ssh = {
      enable = true;
        authorizedKeys = [ # just adds authorized keys for admin user, does not enable ssh!
        "${config.luxnix.generic-settings.rootIdED25519}" 
        ];
      };

    boot.binfmt.emulatedSystems = [
      # "aarch64-linux"
    ];

    luxnix.gpu-eval.enable = lib.mkDefault true;

    roles = { };

    services = {};
    
    environment.systemPackages = with pkgs; [];


    
  };
}
