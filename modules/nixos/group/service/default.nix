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
    enable = mkBoolOpt false "Enable the endoreg-service group";
    name = mkOpt str "endoreg-service" "The name of the group";
    members = mkOpt (listOf str) [
      "admin"
      "endoreg-service-user"
    ] "Groups for the user to be assigned.";
    gid = mkOpt int 101 "The group id";
  };

  config = mkIf cfg.enable {
    users.groups.${cfg.name} =
      {
        name = cfg.name; 
        members = cfg.members;
        gid = cfg.gid;
      };

    users.groups."sslCert" = {
      name = "sslCert";
      members = cfg.members;
    };

    home-manager = {
      # modified due to this warning: evaluation warning: admin profile: You have set either `nixpkgs.config` or `nixpkgs.overlays` while using `home-manager.useGlobalPkgs`.
      useGlobalPkgs = false;
      useUserPackages = true;
    };
  };
}
