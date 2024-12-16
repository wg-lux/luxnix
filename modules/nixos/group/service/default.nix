{
  pkgs,
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.group.endoreg-service;
in {
  options.group.endoreg-service = with types; {
    name = mkOpt str "endoreg-service" "The name of the group";
    # initialPassword =
    #   mkOpt str "1"
    #   "The initial password to use";
    members = mkOpt (listOf str) [
      "admin"
    ] "Groups for the user to be assigned.";
    gid = mkOpt int 101 "The group id";
  };

  config = {
    users.groups.${cfg.name} =
      {
        name = cfg.name; 
        members = cfg.members;
        gid = cfg.gid;
      };

    home-manager = {
      useGlobalPkgs = true;
      useUserPackages = true;
    };
  };
}
