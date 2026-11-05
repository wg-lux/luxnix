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
        assertion = cfg.hashedPasswordFile == null || cfg.requireUsablePasswordFile;
        message = "Client password file validation cannot be disabled.";
      }
      {
        assertion =
          config.users.users.${cfg.name}.hashedPasswordFile == cfg.hashedPasswordFile
          && all (key: config.users.users.${cfg.name}.${key} == null) [
            "password"
            "hashedPassword"
            "initialPassword"
            "initialHashedPassword"
          ];
        message = "Client credentials must use the validated password file; direct user password overrides are refused.";
      }
      {
        assertion =
          !(any (name: builtins.hasAttr name cfg.extraOptions) [
            "password"
            "hashedPassword"
            "hashedPasswordFile"
            "initialPassword"
            "initialHashedPassword"
          ]);
        message = "Configure client credentials through user.client.hashedPasswordFile; extraOptions must not override validation.";
      }
      {
        assertion =
          cfg.hashedPasswordFile == null
          || (hasPrefix "/" cfg.hashedPasswordFile && !hasPrefix "/nix/store/" cfg.hashedPasswordFile);
        message = "Client password file must be an absolute runtime path outside the Nix store.";
      }
      {
        assertion = config.users.mutableUsers || cfg.hashedPasswordFile != null;
        message = "user.client.hashedPasswordFile must be set when users.mutableUsers = false.";
      }
    ];

    system.preSwitchChecks.clientCredential = mkIf (
      cfg.requireUsablePasswordFile && cfg.hashedPasswordFile != null
    ) config.system.activationScripts.luxnixValidateClientPasswordFile.text;

    system.activationScripts = mkIf (cfg.requireUsablePasswordFile && cfg.hashedPasswordFile != null) {
      users.deps = [ "luxnixValidateClientPasswordFile" ];
      luxnixValidateClientPasswordFile = {
        deps = [
          "specialfs"
        ]
        ++ optional (config.system.activationScripts ? setupSecretsForUsers) "setupSecretsForUsers"
        ++ optional (
          config.system.activationScripts ? luxnixPrepareBootAccountHashes
        ) "luxnixPrepareBootAccountHashes";
        text = import ../password-check.nix {
          inherit lib pkgs;
          account = cfg.name;
          passwordFile = cfg.hashedPasswordFile;
        };
      };
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
