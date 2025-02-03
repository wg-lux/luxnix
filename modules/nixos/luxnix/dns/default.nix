{
  lib,
  pkgs,
  config,
  ...
}:
with lib; 
with lib.luxnix; let
  cfg = config.luxnix.dns;

  gs = config.luxnix.generic-settings;

  hosts = {
    "${gs.traefikHostIp}" = [ gs.traefikHostDomain ];
  };

in {
  options.luxnix.dns = {
    enable = mkOption {
      type = types.bool;
      default = true;
      description = ''
        Auto DNS Configuration.
      '';
    };

  };


  config = mkIf cfg.enable {

    networking.hosts = hosts;
  };
}
