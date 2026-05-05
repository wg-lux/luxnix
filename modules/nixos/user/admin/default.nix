{
  pkgs,
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.user.admin;
  # Only reference sslCert group if it exists
  sslCertGroupName =
    if (config.users.groups ? sslCert) then config.users.groups.sslCert.name else null;
  passwordFile = config.luxnix.vault.adminPasswordHashedFile;
  sensitiveServicesGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;

  # passwordFile = "/etc/user-passwords/${cfg.name}_hashed";
in
{
  options.user.admin = with types; {
    name = mkOpt str "admin" "The name of the user's account";
    passwordFile = mkOpt str passwordFile "The hashed password file to use";
    passwordFallback = {
      enable = mkBoolOpt true "Create a known fallback hashed password file when passwordFile is missing.";
      hashedPassword = mkOption {
        type = str;
        default = "$6$yC9hyVoZEYLlzjbZ$pILBYLOZBlplgoYL9L.dyIKPGPrcW2ifd1I3ffRAYIwsv8B.pA76Eo6OUq71gJJKl8kGyBsmlbKwnGcKQEpoa.";
        description = ''
          SHA-512 crypt hash used only as an explicit local recovery fallback.
          This must be a precomputed, known value and must never be randomly
          generated during activation.
        '';
      };
    };
    extraGroups = mkOpt (listOf str) [ ] "Groups for the user to be assigned.";
    extraOptions = mkOpt attrs { } "Extra options passed to users.users.<name>";
  };

  config = {
    assertions = [
      {
        assertion = !cfg.passwordFallback.enable || cfg.passwordFallback.hashedPassword != "";
        message = "user.admin.passwordFallback.hashedPassword must be set when admin password fallback is enabled.";
      }
    ];

    system.activationScripts.createDefaultHashedPasswordAdmin = mkIf cfg.passwordFallback.enable {
      deps = [ "etc" ];
      text = ''
        set -euo pipefail
        password_file=${lib.escapeShellArg cfg.passwordFile}
        if [ ! -s "$password_file" ]; then
          echo "Creating known fallback hashed password file for user ${cfg.name} at $password_file" >&2
          install -d -m 0700 -o root -g root "$(dirname "$password_file")"
          umask 077
          printf '%s\n' ${lib.escapeShellArg cfg.passwordFallback.hashedPassword} > "$password_file"
          chmod 0600 "$password_file"
        fi
      '';
    };
    users.users.${cfg.name} = {
      shell = pkgs.zsh;
      isNormalUser = true;
      hashedPasswordFile = cfg.passwordFile;
      home = "/home/${cfg.name}";
      group = "users";
      linger = true; # Makes sure user services start at boot not at login

      # TODO: set in modules
      extraGroups = [
        "wheel"
        "audio"
        "sound"
        "video"
        "networkmanager"
        "input"
        "tty"
        "podman"
        "kvm"
        "libvirtd"
      ]
      ++ [
        sensitiveServicesGroupName
      ]
      ++ (lib.optional (sslCertGroupName != null) sslCertGroupName)
      ++ cfg.extraGroups
      ++ (lib.optional (config.roles.endoreg-client.adminIsServiceUser or false
      ) config.user.endoreg-service-user.group);
    }
    // cfg.extraOptions;

    home-manager = {
      # modified due to this warning: evaluation warning: admin profile: You have set either `nixpkgs.config` or `nixpkgs.overlays` while using `home-manager.useGlobalPkgs`.
      useGlobalPkgs = false;
      useUserPackages = true;
      backupFileExtension = "backup";
    };
  };
}
