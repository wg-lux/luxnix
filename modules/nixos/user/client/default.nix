{
  pkgs,
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.user.client;
  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
  homeDir = if cfg.home != null then cfg.home else "/home/${cfg.name}";
in
{
  options.user.client = with types; {
    enable = mkBoolOpt false "Enable the client user";
    name = mkOpt str "client-user" "The name of the client-facing user account";
    home = mkOption {
      type = nullOr str;
      default = null;
      description = "Optional override for the client user's home directory";
    };
    hashedPasswordFile = mkOption {
      type = nullOr str;
      default = "/etc/secrets/vault/SCRT_client_user_password_hash";
      description = "Path to a hashed password file for the client user";
    };
    requireUsablePasswordFile = mkBoolOpt true ''
      Refuse activation when the configured hashed password file is missing or empty.
      Disable only for intentionally passwordless client-user deployments.
    '';
    extraGroups = mkOpt (listOf str) [ ] "Additional groups for the client user";
    homeStateVersion = mkOption {
      type = str;
      default = config.system.stateVersion or "24.05";
      description = "home-manager stateVersion for the client user";
    };
    extraOptions = mkOpt attrs { } "Additional users.users options for the client user";
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion = config.users.mutableUsers || cfg.hashedPasswordFile != null;
        message = "user.client.hashedPasswordFile must be set when users.mutableUsers = false.";
      }
    ];

    system.activationScripts.luxnixValidateClientPasswordFile =
      mkIf (cfg.requireUsablePasswordFile && cfg.hashedPasswordFile != null)
        {
          deps = [ "etc" ];
          text = ''
            set -euo pipefail
            client_password_file=${lib.escapeShellArg cfg.hashedPasswordFile}
            if [ ! -s "$client_password_file" ]; then
              echo "ERROR: client user password hash file is missing or empty: $client_password_file" >&2
              echo "Refusing activation to avoid switching into a generation with an unusable client password." >&2
              exit 1
            fi
          '';
        };

    users.users.${cfg.name} = {
      isNormalUser = true;
      createHome = true;
      home = homeDir;
      shell = pkgs.zsh;
      group = "users";
      extraGroups = [
        sensitiveServiceGroupName
        "endoreg-service"
      ]
      ++ cfg.extraGroups;
    }
    // optionalAttrs (cfg.hashedPasswordFile != null) {
      inherit (cfg) hashedPasswordFile;
    }
    // cfg.extraOptions;

    home-manager = {
      useGlobalPkgs = false;
      useUserPackages = true;
      backupFileExtension = "backup";
    };
  };
}
