{
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.security.luxnix.local-users;
  hostname = config.networking.hostName;
  isGcHost = hasPrefix "gc-" hostname;
  adminPassword = cfg.adminPassword;
  clientPassword = cfg.clientPassword;
  fallbackHash = "$6$yC9hyVoZEYLlzjbZ$pILBYLOZBlplgoYL9L.dyIKPGPrcW2ifd1I3ffRAYIwsv8B.pA76Eo6OUq71gJJKl8kGyBsmlbKwnGcKQEpoa.";
  adminPasswordFile =
    if adminPassword.source == "sops" then
      config.sops.secrets.${adminPassword.sops.secretName}.path
    else
      adminPassword.hashedFile;
  clientPasswordFile =
    if clientPassword.source == "sops" then
      config.sops.secrets.${clientPassword.sops.secretName}.path
    else
      clientPassword.hashedFile;
  fallbackCanInstall = adminPassword.source == "vault-file" && adminPassword.fallback.enable;
in
{
  options.security.luxnix.local-users = {
    enable = mkBoolOpt isGcHost "Whether to manage local-user password safety policy.";

    adminPassword = with types; {
      source = mkOption {
        type = enum [
          "vault-file"
          "sops"
        ];
        default = "vault-file";
        description = ''
          Source for the admin account password hash. "vault-file" points at an
          existing runtime file, while "sops" declares a sops-nix secret whose
          content is the hashed password.
        '';
      };

      hashedFile = mkOption {
        type = str;
        default = config.luxnix.vault.adminPasswordHashedFile;
        description = "Runtime path containing the admin user's hashed password.";
      };

      allowGenerated = mkBoolOpt false "Permit generated admin passwords during activation. This is intentionally refused.";

      requireUsableFile = mkBoolOpt true "Refuse activation when a non-fallback password file source is missing or empty.";

      fallback = {
        enable = mkBoolOpt isGcHost "Install a known local fallback hash if the vault-file hash is missing.";
        hashedPassword = mkOption {
          type = str;
          default = fallbackHash;
          description = ''
            Known SHA-512 crypt hash used as the emergency local fallback on GC
            workstations. This is intentionally static and precomputed; activation
            must never generate a new password.
          '';
        };
      };

      sops = {
        secretName = mkOption {
          type = str;
          default = "admin-password-hash";
          description = "sops-nix secret name containing the admin password hash.";
        };

        key = mkOption {
          type = nullOr str;
          default = null;
          description = "Optional key inside the SOPS file. Defaults to secretName.";
        };

        sopsFile = mkOption {
          type = nullOr path;
          default = null;
          description = "SOPS file containing the admin password hash secret.";
        };
      };
    };

    clientPassword = with types; {
      source = mkOption {
        type = enum [
          "vault-file"
          "sops"
        ];
        default = "vault-file";
        description = ''
          Source for the client user password hash. "vault-file" points at an
          existing runtime file, while "sops" declares a sops-nix secret whose
          content is the hashed password.
        '';
      };

      hashedFile = mkOption {
        type = str;
        default = "${config.luxnix.vault.dir}/SCRT_client_user_password_hash";
        description = "Runtime path containing the client user's hashed password.";
      };

      requireUsableFile = mkBoolOpt true "Refuse activation when the client user's password hash file is missing or empty.";

      sops = {
        secretName = mkOption {
          type = str;
          default = "client-user-password-hash";
          description = "sops-nix secret name containing the client user password hash.";
        };

        key = mkOption {
          type = nullOr str;
          default = null;
          description = "Optional key inside the SOPS file. Defaults to secretName.";
        };

        sopsFile = mkOption {
          type = nullOr path;
          default = null;
          description = "SOPS file containing the client user password hash secret.";
        };
      };
    };

    firmwarePassword = {
      manage = mkBoolOpt false "Allow LuxNix to manage BIOS/UEFI firmware passwords. This is intentionally refused.";
      allowGenerated = mkBoolOpt false "Permit generated BIOS/UEFI passwords. This is intentionally refused.";
    };
  };

  config = mkIf cfg.enable (mkMerge [
    {
      assertions = [
        {
          assertion = !adminPassword.allowGenerated;
          message = "LuxNix refuses generated admin passwords. Provide a known hashed file or a SOPS-managed hash.";
        }
        {
          assertion = adminPassword.source != "sops" || adminPassword.sops.sopsFile != null;
          message = "security.luxnix.local-users.adminPassword.sops.sopsFile must be set when source = \"sops\".";
        }
        {
          assertion = adminPassword.source != "sops" || !adminPassword.fallback.enable;
          message = "Admin password fallback writes only to vault-file sources. Disable fallback when source = \"sops\".";
        }
        {
          assertion = clientPassword.source != "sops" || clientPassword.sops.sopsFile != null;
          message = "security.luxnix.local-users.clientPassword.sops.sopsFile must be set when source = \"sops\".";
        }
        {
          assertion = !cfg.firmwarePassword.manage;
          message = "LuxNix intentionally does not manage BIOS/UEFI passwords; keep firmware passwords in an out-of-band recovery record.";
        }
        {
          assertion = !cfg.firmwarePassword.allowGenerated;
          message = "LuxNix refuses generated BIOS/UEFI passwords because losing one can permanently lock a workstation.";
        }
      ];

      users.mutableUsers = mkDefault false;

      user.admin = {
        passwordFile = adminPasswordFile;
        passwordFallback = {
          enable = fallbackCanInstall;
          hashedPassword = adminPassword.fallback.hashedPassword;
        };
      };

      user.client = mkIf config.user.client.enable {
        hashedPasswordFile =
          if clientPassword.source == "sops" then
            mkForce clientPasswordFile
          else
            mkDefault clientPasswordFile;
        requireUsablePasswordFile = clientPassword.requireUsableFile;
      };

      system.activationScripts.luxnixValidateAdminPasswordFile =
        mkIf
          (adminPassword.requireUsableFile && !fallbackCanInstall && adminPassword.source == "vault-file")
          {
            deps = [ "etc" ];
            text = ''
              set -euo pipefail
              admin_password_file=${lib.escapeShellArg adminPasswordFile}
              if [ ! -s "$admin_password_file" ]; then
                echo "ERROR: admin password hash file is missing or empty: $admin_password_file" >&2
                echo "Refusing activation to avoid switching into a generation with an unusable admin password." >&2
                exit 1
              fi
            '';
          };
    }

    (mkIf (adminPassword.source == "sops") {
      sops.secrets.${adminPassword.sops.secretName} = {
        neededForUsers = true;
      }
      // optionalAttrs (adminPassword.sops.sopsFile != null) {
        sopsFile = adminPassword.sops.sopsFile;
      }
      // optionalAttrs (adminPassword.sops.key != null) {
        key = adminPassword.sops.key;
      };
    })

    (mkIf (clientPassword.source == "sops") {
      sops.secrets.${clientPassword.sops.secretName} = {
        neededForUsers = true;
      }
      // optionalAttrs (clientPassword.sops.sopsFile != null) {
        sopsFile = clientPassword.sops.sopsFile;
      }
      // optionalAttrs (clientPassword.sops.key != null) {
        key = clientPassword.sops.key;
      };
    })
  ]);
}
