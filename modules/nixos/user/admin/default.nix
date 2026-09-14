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
      enable = mkBoolOpt false "Legacy shared password fallback; enabling it is refused.";
      hashedPassword = mkOption {
        type = str;
        default = "";
        description = "Removed inline fallback hash. Provision a unique root-only runtime hash file instead.";
      };
    };
    extraGroups = mkOpt (listOf str) [ ] "Groups for the user to be assigned.";
    extraOptions = mkOpt attrs { } "Extra options passed to users.users.<name>";
  };

  config = {
    assertions = [
      {
        assertion = !cfg.passwordFallback.enable && cfg.passwordFallback.hashedPassword == "";
        message = "Shared admin password fallback is removed. Provision a unique root-only runtime hash file, and verify independent SSH recovery before deployment.";
      }
      {
        assertion = hasPrefix "/" cfg.passwordFile && !hasPrefix "/nix/store/" cfg.passwordFile;
        message = "user.admin.passwordFile must be an absolute runtime path outside the Nix store.";
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
        message = "Configure admin credentials through user.admin.passwordFile; extraOptions must not override password validation.";
      }
      {
        assertion = !config.systemd.sysusers.enable && !config.services.userborn.enable;
        message = "Admin password validation requires the NixOS users activation backend.";
      }
    ];

    # Abort the entire activation before users can change /etc/shadow. Keep the
    # existing account and independent authorized SSH keys available on failure.
    system.activationScripts.users.deps = [ "luxnixValidateAdminPasswordFile" ];
    system.activationScripts.luxnixValidateAdminPasswordFile = {
      deps = [
        "specialfs"
      ]
      ++ optional (config.system.activationScripts ? setupSecretsForUsers) "setupSecretsForUsers";
      text = ''
        admin_password_file=${lib.escapeShellArg cfg.passwordFile}
        if [ ! -f "$admin_password_file" ] || [ ! -s "$admin_password_file" ]; then
          echo "ERROR: admin password hash file is missing, empty, or not a regular file; refusing account activation." >&2
          exit 1
        fi
        admin_password_metadata=$(${pkgs.coreutils}/bin/stat -Lc '%u:%a' -- "$admin_password_file") || exit 1
        case "$admin_password_metadata" in
          0:400|0:600) ;;
          *) echo "ERROR: admin password hash must be root-owned with mode 0400 or 0600." >&2; exit 1 ;;
        esac
        # Only supported modern crypt encodings, exactly one nonempty line.
        # Neither the hash nor its value is ever emitted in diagnostics.
        if ! ${pkgs.gnugrep}/bin/grep -qxE '\$6\$(rounds=[0-9]+\$)?[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}|\$y\$[./A-Za-z0-9]+\$[./A-Za-z0-9]+\$[./A-Za-z0-9]{43}' "$admin_password_file" ||
           [ "$(${pkgs.gawk}/bin/awk 'END { print NR }' "$admin_password_file")" -ne 1 ]; then
          echo "ERROR: admin password file must contain one SHA-512 crypt or yescrypt hash; refusing account activation." >&2
          exit 1
        fi
        # Refuse the retired repository-wide credential even if an earlier
        # generation already installed it into the runtime file.
        admin_password_fingerprint=$(${pkgs.gawk}/bin/awk '{ printf "%s", $0 }' "$admin_password_file" | ${pkgs.coreutils}/bin/sha256sum) || exit 1
        case "$admin_password_fingerprint" in
          a396e38d2c16276942366260dfc8e88ccef88e5df8915d50e688aca7e1502bba*)
            echo "ERROR: retired shared admin password detected; provision a unique host credential before activation." >&2
            exit 1
            ;;
        esac
      '';
    };
    users.users.${cfg.name} = {
      shell = pkgs.zsh;
      isNormalUser = true;
      hashedPasswordFile = cfg.passwordFile;
      home = "/home/${cfg.name}";
      group = "users";
      linger = true; # Makes sure user services start at boot not at login

      # TODO (user-role owner): this legacy aggregate grants role-specific
      # groups eagerly; move each group contribution into its owning module.
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
