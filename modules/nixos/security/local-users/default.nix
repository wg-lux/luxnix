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
  inherit (cfg) adminPassword clientPassword;
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

      requireUsableFile = mkBoolOpt true "Require a valid root-only admin hash file before account activation. Disabling this check is refused.";

      fallback = {
        enable = mkBoolOpt false "Legacy shared password fallback; enabling it is refused.";
        hashedPassword = mkOption {
          type = str;
          default = "";
          description = "Removed inline fallback hash. Provision a unique root-only runtime hash file instead.";
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
          assertion = adminPassword.requireUsableFile;
          message = "Admin password file validation cannot be disabled.";
        }
        {
          assertion = !adminPassword.allowGenerated;
          message = "LuxNix refuses generated admin passwords. Provide a known hashed file or a SOPS-managed hash.";
        }
        {
          assertion = adminPassword.source != "sops" || adminPassword.sops.sopsFile != null;
          message = "security.luxnix.local-users.adminPassword.sops.sopsFile must be set when source = \"sops\".";
        }
        {
          assertion = !adminPassword.fallback.enable && adminPassword.fallback.hashedPassword == "";
          message = "Shared admin password fallback is removed. Provision a unique root-only runtime hash file.";
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
      };

      user.client = mkIf config.user.client.enable {
        hashedPasswordFile =
          if clientPassword.source == "sops" then
            mkForce clientPasswordFile
          else
            mkDefault clientPasswordFile;
        requireUsablePasswordFile = clientPassword.requireUsableFile;
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
