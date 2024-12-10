{
  pkgs,
  config,
  lib,
  ...
}:
#CHANGEME SETUP VPN
with lib; let
  cfg = config.services.vpn;
in {
  options.services.vpn = {
    enable = mkEnableOption "Enable vpn";

    main-domain = mkOption {
      type = types.str;
      default = "vpn.luxnix.org";
      description = "The main domain for the vpn";
    };

    backup-nameservers = mkOption {
      type = types.listOf types.str;
      default = ["8.8.8.8" "1.1.1.1"];
      description = "The nameservers for the vpn";
    };

    stage-1-vpn = mkOption {
      type = types.bool;
      default = false;
      description = "Enabbles VPN Service at stage 1 of boot";
    };

  };

  config = mkIf cfg.enable {
    networking.domain = cfg.main-domain;
    networking.nameservers = [ "8.8.8.8" "1.1.1.1" ];

  
  };
}
