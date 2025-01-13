{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.lx-anonymizer;
in {
  options.roles.lx-anonymizer = {
    enable = mkBoolOpt false ''
      Enable LX-Anonymizer installation / setup / configuration.
    '';

    rootDir = mkOption {
      type = types.str;
      default = "/etc/lx-anonymizer";
      description = ''
        The root directory for the LX-Anonymizer installation.
      '';
    };
    
    user = mkOption {
      type = types.str;
      default = "lxAnonymizer";
      description = ''
        The user to run the LX-Anonymizer service.
      '';
    };

    group = mkOption {
      type = types.str;
      default = "lxAnonymizer";
      description = ''
        The group to run the LX-Anonymizer service.
      '';

    };
  };

  config = mkIf cfg.enable {
    # use tmpfile rules to create root dir and data as well as tmp subdirs

    systemd.tmpfiles.rules = [
      "d ${cfg.rootDir} 0700 ${cfg.user} ${cfg.group} -"
      "d ${cfg.rootDir}/data 0700 ${cfg.user} ${cfg.group} -"
      "d ${cfg.rootDir}/tmp 0700 ${cfg.user} ${cfg.group} -"
    ];

    # TODO Create user with correct permissions

  };
}
