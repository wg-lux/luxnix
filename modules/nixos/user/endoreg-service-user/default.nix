{
  pkgs,
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.user.endoreg-service-user;
in {
  options.user.endoreg-service-user = with types; {
    name = mkOpt str "endoreg-service-user" "The name of the user's account";
    enable = mkBoolOpt false "Enable the user";
    extraGroups = mkOpt (listOf str) [] "Groups for the user to be assigned.";
    extraOptions =
      mkOpt attrs {}
      "Extra options passed to users.users.<name>";
  };

  config = mkIf cfg.enable {
    users.users.${cfg.name} =
      {
        shell = pkgs.zsh;
        isSystemUser = true;
        createHome = true;
        home = "/home/${cfg.name}";
        group = "endoreg-service";
        homeMode = "0750";
        uid = 400;

        # TODO: set in modules
        extraGroups =
          [
          ]
          ++ cfg.extraGroups;
      }
      // cfg.extraOptions;

    home-manager = {
      useGlobalPkgs = true;
      useUserPackages = true;
    };
  };
}
