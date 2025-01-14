{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.luxnix.generic-settings.uids;

  userConfigs = [
    {
      condition = config.roles.lx-anonymizer.enable;
      user = config.roles.lx-anonymizer.user;
      uid = cfg.lxAnonymizer;
    }
    # Add more user configurations here
    # {
    #   condition = config.roles.someOtherRole.enable;
    #   user = config.roles.someOtherRole.user;
    #   uid = cfg.someOtherUid;
    # }
  ];

  generateUserConfig = userConfig: mkIf userConfig.condition {
    users.users.${userConfig.user}.uid = userConfig.uid;
  };

in {
  options.luxnix.generic-settings.uids = { 
    lxAnonymizer = mkOption {
      type = types.int;
      default = 731;
      description = "UID for lxAnonymizer";
    };
    # Add more options here
    # someOtherUid = mkOption {
    #   type = types.int;
    #   default = 732;
    #   description = "UID for some other user";
    # };
  };

  config = foldl' (acc: userConfig: acc // generateUserConfig userConfig) {} userConfigs;
}

