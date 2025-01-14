{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.luxnix.generic-settings.uids;

in {
  options.luxnix.generic-settings.uids = { 
    lxAnonymizer = mkOption {
      type = types.int;
      default = 731;
      description = "UID for lxAnonymizer";
    };
  };

  config = {
    users.users.${config.roles.lx-anonymizer.user}.uid = cfg.lxAnonymizer;
    
  };
}

