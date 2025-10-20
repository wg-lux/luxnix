{ pkgs
, config
, lib
, ...
}:
with lib;
with lib.luxnix; let
  cfg = config.user.client;
  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
  homeDir = if cfg.home != null then cfg.home else "/home/${cfg.name}";
in {
  options.user.client = with types; {
    enable = mkBoolOpt false "Enable the client user";
    name = mkOpt str "client-user" "The name of the client-facing user account";
    home = mkOption {
      type = nullOr str;
      default = null;
      description = "Optional override for the client user's home directory";
    };
    hashedPasswordFile = mkOption {
      type = nullOr path;
      default = null;
      description = "Path to a hashed password file for the client user";
    };
    extraGroups = mkOpt (listOf str) [] "Additional groups for the client user";
    homeStateVersion = mkOption {
      type = str;
      default = (config.system.stateVersion or "24.05");
      description = "home-manager stateVersion for the client user";
    };
    extraOptions = mkOpt attrs { } "Additional users.users options for the client user";
  };

  config = mkIf cfg.enable {
    users.users.${cfg.name} =
      {
        isNormalUser = true;
        createHome = true;
        home = homeDir;
        shell = pkgs.zsh;
        group = "users";
        extraGroups = [
          sensitiveServiceGroupName
          "endoreg-service"
        ] ++ cfg.extraGroups;
      }
      // optionalAttrs (cfg.hashedPasswordFile != null) {
        hashedPasswordFile = cfg.hashedPasswordFile;
      }
      // cfg.extraOptions;

    home-manager = {
      useGlobalPkgs = false;
      useUserPackages = true;
    };
  };
}
