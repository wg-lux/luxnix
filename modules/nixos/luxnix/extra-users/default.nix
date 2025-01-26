{
  lib,
  pkgs,
  config,
  ...
}:
with lib; 
with lib.luxnix; let
  cfg = config.luxnix.extraUsers;

############################################
#  Documentation
############################################
# users.extraUsers.<name>.linger: 
# Whether to enable lingering for this user. 
# If true, systemd user units will start at boot, rather than starting at 
# login and stopping at logout. This is the declarative equivalent of running 
# loginctl enable-linger for this user.
# If false, user units will not be started until the user logs in, and may be 
# stopped on logout depending on the settings in 

in {
  options.luxnix.extraUsers = {
    enable = mkOption {
      type = types.bool;
      default = true;
      description = ''
        Enable the extra users configuration.
      '';
    };

    extraUsers = mkOption {
      type = types.attrs;
      default = {};
      description = ''
        A set of users to create.
        Is passed to users.extraUsers, common options are:
        - name
        - linger (default: false)
        - openssh.authorizedKeys.keys
        - openssh.authorizedKeys.keyFiles
        - shell
        - uid # if set, the user will be created with this uid 
          >1000 are normal users; <1000 are system users
          if set options "isSystemUser" and "isNormalUser" are ignored
          otherwise one of them must be set to true

        - group
        - extraGroups
        - useDefaultShell
      '';
    };
  };


  config = mkIf cfg.enable {

    users.extraUsers = cfg.extraUsers;

    
  };
}
