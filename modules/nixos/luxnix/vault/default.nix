{
  lib,
  pkgs,
  config,
  ...
}:
with lib; 
with lib.luxnix; let
  cfg = config.luxnix.vault;
  adminName = config.user.admin.name;
  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;

  sslCertGroupName = "sslCert";

in {
  options.luxnix.vault = {
    enable = mkEnableOption "Enable Default Vault configuration";
    dir = mkOption {
      default = "${config.luxnix.generic-settings.secretDir}/vault";
      type = types.str;
      description = "The directory where Vault configuration files are stored";
    };

    adminPasswordFile = mkOption {
      default = "${config.luxnix.vault.dir}/SCRT_local_password_${adminName}_password";
      type = types.str;
      description = "The path to the admin password file";
    };

    adminPasswordHashedFile = mkOption {
      default = "${config.luxnix.vault.adminPasswordFile}_hash";
      type = types.str;
      description = "The path to the admin password hashed file";
    };

    key = mkOption { # DEPRECATED ?
      default = "${config.luxnix.generic-settings.secretDir}/.key";
      type = types.str;
      description = "The path to the key file";
    };

    psk = mkOption {
      default = "${config.luxnix.generic-settings.secretDir}/.psk";
      type = types.str;
      description = "The path to the psk file";
    };

    sslCert = mkOption {
      default = "${cfg.dir}/ssl_cert";
      type = types.str;
      description = "Path to SSL certificate in vault";
    };

    sslKey = mkOption {
      default = "${cfg.dir}/ssl_key";
      type = types.str;
      description = "Path to SSL key in vault";
    };

  };


  config = mkIf cfg.enable {
    # make sure vault dir exists with correct permissions (700) #FIXME
    systemd.tmpfiles.rules = [
      "d ${cfg.dir} 0770 ${adminName} ${sensitiveServiceGroupName}"
    ];
  };
}
