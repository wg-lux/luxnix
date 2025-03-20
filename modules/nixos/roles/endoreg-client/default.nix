{ lib
, config
, pkgs
, ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.endoreg-client;


  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
in
{
  options.roles.endoreg-client = {
    enable = mkEnableOption "Enable endoreg client configuration";

    dbApiLocal = mkOption {
      type = types.bool;
      default = false;
      description = "Enable local endoreg-db-api service";
    };
  };

  config = mkIf cfg.enable {
    user.endoreg-service-user.enable = true;

    roles = {
      desktop.enable = true;
      custom-packages.cuda = true;
      aglnet.client.enable = true;
    };

    luxnix.nvidia-prime.enable = true;

    services.luxnix.endoregDbApiLocal = {
      enable = cfg.dbApiLocal;
    };

    services.ssh = {
      enable = true;
      authorizedKeys = [
        # just adds authorized keys for admin user, does not enable ssh!
        "${config.luxnix.generic-settings.rootIdED25519}"
      ];
    };

    systemd.tmpfiles.rules = [
      # USB Encrypter
      "d /mnt/endoreg-sensitive-data 0770 root ${sensitiveServiceGroupName} -"
    ];
  };
}
