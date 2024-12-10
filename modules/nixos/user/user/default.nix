{
  pkgs,
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.user.user;
in {
  options.user.user = with types; {
    enable = mkBoolOpt true "Enable basic center User";
    name = mkOpt str "endoreg-center" "The name of the user's account";
    initialPassword =
      mkOpt str "1"
      "The initial password to use";
    extraGroups = mkOpt (listOf str) [] "Groups for the user to be assigned.";
    extraOptions =
      mkOpt attrs {}
      "Extra options passed to users.users.<name>";
  };

  config = mkIf cfg.enable {
    users.users.${cfg.name} =
      {
        shell = pkgs.zsh;
        isNormalUser = true;
        inherit (cfg) name initialPassword;
        home = "/home/${cfg.name}";
        group = "users";

        # TODO: set in modules
        extraGroups =
          [
            "audio"
            "sound"
            "video"
            "networkmanager"
            "libvirtd"
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
