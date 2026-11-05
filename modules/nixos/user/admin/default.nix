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
  # SHA-256 of the public retired shared admin hash and that hash's salt; the
  # credential itself is not kept here. Mirrors lx_administration/storage/operator_migration.py.
  retiredAdminHashSha256 = "a396e38d2c16276942366260dfc8e88ccef88e5df8915d50e688aca7e1502bba";
  retiredAdminSalt = "yC9hyVoZEYLlzjbZ";

  # Interactive replacement for a missing, malformed or retired admin hash. It
  # asks on the current terminal or through systemd password agents and never
  # takes the password from arguments or the environment.
  adminPasswordTool = pkgs.writeShellApplication {
    name = "luxnix-admin-password";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.openssl
      pkgs.shadow
      pkgs.systemd
    ];
    text = ''
      umask 077
      if [ "$(id -u)" -ne 0 ]; then
        echo "ERROR: run as root: sudo luxnix-admin-password" >&2
        exit 2
      fi
      # shellcheck disable=SC2209
      account=${escapeShellArg cfg.name}
      host=${escapeShellArg config.networking.hostName}
      boot_hash_file=${escapeShellArg cfg.passwordFile}
      vault_hash_file=${escapeShellArg config.luxnix.vault.adminPasswordHashedFile}
      vault_password_file=${escapeShellArg config.luxnix.vault.adminPasswordFile}
      retired_salt=${escapeShellArg retiredAdminSalt}
      retired_digest=${escapeShellArg retiredAdminHashSha256}

      # Plaintext may only be written to unlocked encrypted storage.
      encrypted() {
        PATH="${makeBinPath [ pkgs.util-linux ]}:$PATH" \
          ${pkgs.python3}/bin/python3 ${../../../../lx_administration/secret_storage.py} \
          --allow-runtime "$1" >/dev/null 2>&1
      }

      write_private() {
        local directory temporary
        directory="$(dirname "$1")"
        [ -d "$directory" ] || mkdir -m 0700 "$directory"
        temporary="$(mktemp "$directory/.luxnix-admin-password.XXXXXX")"
        printf '%s\n' "$2" > "$temporary"
        chown root:root "$temporary"
        chmod 0600 "$temporary"
        mv -f "$temporary" "$1"
      }

      ask() {
        systemd-ask-password --timeout=300 --id="luxnix-admin-password:$host" "$1"
      }

      reject() {
        notice="Rejected: $1. "
        echo "$notice" >&2
      }

      echo "Set a new password for '$account' on $host." >&2
      echo "If no prompt appears here, answer it within 5 minutes from another terminal on $host: sudo systemd-tty-ask-password-agent" >&2
      notice=""
      for attempt in 1 2 3; do
        if ! password="$(ask "''${notice}New password for $account on $host (attempt $attempt/3; at least 12 bytes; not the retired shared password, which may still be your current sudo password):")" ||
           ! repeat="$(ask "Repeat the new password for $account on $host:")"; then
          echo "ERROR: no password was entered." >&2
          exit 1
        fi
        if [ "$password" != "$repeat" ]; then
          reject "the two entries did not match"
          continue
        fi
        if [ "$(printf '%s' "$password" | LC_ALL=C wc -c)" -lt 12 ]; then
          reject "shorter than 12 bytes"
          continue
        fi
        if [ "$(printf '%s\n' "$password" | openssl passwd -6 -salt "$retired_salt" -stdin | tr -d '\n' | sha256sum | cut -d ' ' -f 1)" = "$retired_digest" ]; then
          reject "that is the retired shared password; choose a unique one"
          continue
        fi
        hash="$(printf '%s\n' "$password" | openssl passwd -6 -stdin)"

        write_private "$boot_hash_file" "$hash"
        if [ "$vault_hash_file" != "$boot_hash_file" ] && encrypted "$vault_hash_file"; then
          write_private "$vault_hash_file" "$hash"
        fi
        if encrypted "$vault_password_file"; then
          write_private "$vault_password_file" "$password"
        else
          echo "NOTE: $vault_password_file is not on unlocked encrypted storage and was left unchanged." >&2
        fi
        unset password repeat
        printf '%s:%s\n' "$account" "$hash" | chpasswd -e
        echo "New password for '$account' installed in $boot_hash_file." >&2
        echo "Store it in the password manager and import it into the controller vault (docs/admin-passwords.md); otherwise sync-secrets redeploys the older pair." >&2
        exit 0
      done
      echo "ERROR: no acceptable password after three attempts (last: ''${notice:-none})." >&2
      exit 1
    '';
  };

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
        assertion =
          config.users.users.${cfg.name}.hashedPasswordFile == cfg.passwordFile
          && all (key: config.users.users.${cfg.name}.${key} == null) [
            "password"
            "hashedPassword"
            "initialPassword"
            "initialHashedPassword"
          ];
        message = "Admin credentials must use the validated password file; direct user password overrides are refused.";
      }
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

    environment.systemPackages = [ adminPasswordTool ];

    # Abort the entire activation before users can change /etc/shadow. Keep the
    # existing account and independent authorized SSH keys available on failure.
    system = {
      preSwitchChecks.adminCredential =
        config.system.activationScripts.luxnixValidateAdminPasswordFile.text;
      activationScripts.users.deps = [ "luxnixValidateAdminPasswordFile" ];
      activationScripts.luxnixValidateAdminPasswordFile = {
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
          inherit (cfg) passwordFile;
        };
      };
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
