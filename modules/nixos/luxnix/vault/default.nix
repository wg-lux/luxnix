{
  lib,
  pkgs,
  config,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.luxnix.vault;
  adminName = config.user.admin.name;
  runtimeDir = "/run/luxnix/vault";
  runtimeEnvironmentFile = "${runtimeDir}/vault.env";
  runtimeTokenFile = "${runtimeDir}/vault.token";
  vaultAuthEnabled = cfg.enable && cfg.client.enable && cfg.client.auth.method != "none";

  vaultAuthSetupScript = pkgs.writeShellScript "luxnix-vault-auth-setup" ''
    set -euo pipefail
    umask 077

    RUNTIME_DIR="${runtimeDir}"
    TOKEN_FILE="${runtimeTokenFile}"
    ENV_FILE="${runtimeEnvironmentFile}"
    TMP_ENV="$(mktemp "$RUNTIME_DIR/.vault.env.XXXXXX")"
    TMP_TOKEN="$(mktemp "$RUNTIME_DIR/.vault.token.XXXXXX")"
    trap 'rm -f "$TMP_ENV" "$TMP_TOKEN"' EXIT

    mkdir -p "$RUNTIME_DIR"
    chmod 0700 "$RUNTIME_DIR"

    ${optionalString (cfg.client.address != null) ''
      export VAULT_ADDR=${lib.escapeShellArg cfg.client.address}
    ''}
    ${optionalString (cfg.client.caCertFile != null) ''
      export VAULT_CACERT=${lib.escapeShellArg (toString cfg.client.caCertFile)}
    ''}

    if [ -z "''${VAULT_ADDR:-}" ]; then
      echo "ERROR: VAULT_ADDR is not set for Vault authentication." >&2
      exit 1
    fi

    case "${cfg.client.auth.method}" in
      tokenFile)
        SOURCE_TOKEN_FILE=${lib.escapeShellArg (toString cfg.client.auth.tokenFile)}
        if [ ! -f "$SOURCE_TOKEN_FILE" ]; then
          echo "ERROR: Vault token file $SOURCE_TOKEN_FILE does not exist." >&2
          exit 1
        fi
        tr -d '\n' < "$SOURCE_TOKEN_FILE" > "$TMP_TOKEN"
        ;;
      approle)
        ROLE_ID_FILE=${lib.escapeShellArg (toString cfg.client.auth.roleIdFile)}
        SECRET_ID_FILE=${lib.escapeShellArg (toString cfg.client.auth.secretIdFile)}
        if [ ! -f "$ROLE_ID_FILE" ] || [ ! -f "$SECRET_ID_FILE" ]; then
          echo "ERROR: Vault AppRole files are missing." >&2
          exit 1
        fi
        ROLE_ID="$(tr -d '\n' < "$ROLE_ID_FILE")"
        SECRET_ID="$(tr -d '\n' < "$SECRET_ID_FILE")"
        ${pkgs.vault}/bin/vault write -field=token auth/approle/login \
          role_id="$ROLE_ID" \
          secret_id="$SECRET_ID" > "$TMP_TOKEN"
        ;;
      *)
        echo "ERROR: Unsupported Vault auth method ${cfg.client.auth.method}." >&2
        exit 1
        ;;
    esac

    chmod 0600 "$TMP_TOKEN"
    mv -f "$TMP_TOKEN" "$TOKEN_FILE"
    chmod 0600 "$TOKEN_FILE"

    {
      printf 'VAULT_ADDR=%s\n' "''${VAULT_ADDR}"
      printf 'VAULT_TOKEN=%s\n' "$(${pkgs.coreutils}/bin/cat "$TOKEN_FILE")"
      if [ -n "''${VAULT_CACERT:-}" ]; then
        printf 'VAULT_CACERT=%s\n' "''${VAULT_CACERT}"
      fi
    } > "$TMP_ENV"

    chmod 0600 "$TMP_ENV"
    mv -f "$TMP_ENV" "$ENV_FILE"
    chmod 0600 "$ENV_FILE"
    trap - EXIT
  '';

  vaultAuthCleanupScript = pkgs.writeShellScript "luxnix-vault-auth-cleanup" ''
    set -euo pipefail
    rm -f ${lib.escapeShellArg runtimeEnvironmentFile} ${lib.escapeShellArg runtimeTokenFile}
  '';
in
{
  options.luxnix.vault = {
    enable = mkEnableOption "Enable Default Vault configuration";
    dir = mkOption {
      default = "${config.luxnix.generic-settings.secretDir}/vault";
      type = types.str;
      description = "The directory where Vault configuration files are stored";
    };

    adminPasswordFile = mkOption {
      default = "${config.luxnix.vault.dir}/SCRT_local_password_${adminName}_password";
      type = types.str;
      description = "The path to the admin password file";
    };

    adminPasswordHashedFile = mkOption {
      default = "${config.luxnix.vault.adminPasswordFile}_hash";
      type = types.str;
      description = "The path to the admin password hashed file";
    };

    key = mkOption {
      default = "${config.luxnix.generic-settings.secretDir}/.key";
      type = types.str;
      description = "The path to the key file";
    };

    psk = mkOption {
      default = "${config.luxnix.generic-settings.secretDir}/.psk";
      type = types.str;
      description = "The path to the psk file";
    };

    sslCert = mkOption {
      default = "${cfg.dir}/ssl_cert";
      type = types.str;
      description = "Path to SSL certificate in vault";
    };

    sslKey = mkOption {
      default = "${cfg.dir}/ssl_key";
      type = types.str;
      description = "Path to SSL key in vault";
    };

    client = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = true;
            description = "Enable runtime Vault client bootstrap for systemd services.";
          };

          address = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Vault server address exported as VAULT_ADDR.";
          };

          caCertFile = mkOption {
            type = types.nullOr types.path;
            default = null;
            description = "Optional CA certificate exported as VAULT_CACERT.";
          };

          environmentFile = mkOption {
            type = types.nullOr types.path;
            default = null;
            description = "Optional existing environment file loaded before Vault auth bootstrap.";
          };

          runtimeEnvironmentFile = mkOption {
            type = types.str;
            default = runtimeEnvironmentFile;
            readOnly = true;
            description = "Generated runtime environment file containing VAULT_ADDR and VAULT_TOKEN.";
          };

          runtimeTokenFile = mkOption {
            type = types.str;
            default = runtimeTokenFile;
            readOnly = true;
            description = "Generated runtime token file used by LuxNix systemd services.";
          };

          auth = mkOption {
            type = types.submodule {
              options = {
                method = mkOption {
                  type = types.enum [ "none" "tokenFile" "approle" ];
                  default = "none";
                  description = "Vault auth method used for system services.";
                };

                tokenFile = mkOption {
                  type = types.nullOr types.path;
                  default = null;
                  description = "Root-readable file containing a Vault token.";
                };

                roleIdFile = mkOption {
                  type = types.nullOr types.path;
                  default = null;
                  description = "Root-readable file containing a Vault AppRole role_id.";
                };

                secretIdFile = mkOption {
                  type = types.nullOr types.path;
                  default = null;
                  description = "Root-readable file containing a Vault AppRole secret_id.";
                };
              };
            };
            default = { };
            description = "Vault authentication bootstrap for LuxNix systemd services.";
          };
        };
      };
      default = { };
      description = "Vault client configuration used by secret-provisioning services.";
    };
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion =
          !vaultAuthEnabled
          || cfg.client.address != null
          || cfg.client.environmentFile != null;
        message = "luxnix.vault.client.address or luxnix.vault.client.environmentFile must be set when Vault auth bootstrap is enabled.";
      }
      {
        assertion =
          cfg.client.auth.method != "tokenFile"
          || cfg.client.auth.tokenFile != null;
        message = "luxnix.vault.client.auth.tokenFile must be set when auth.method = \"tokenFile\".";
      }
      {
        assertion =
          cfg.client.auth.method != "approle"
          || (cfg.client.auth.roleIdFile != null && cfg.client.auth.secretIdFile != null);
        message = "luxnix.vault.client.auth.roleIdFile and secretIdFile must be set when auth.method = \"approle\".";
      }
    ];

    systemd.tmpfiles.rules = [
      "d ${runtimeDir} 0700 root root - -"
      "z ${runtimeDir} 0700 root root - -"
    ];

    systemd.services.vault-auth-setup = mkIf vaultAuthEnabled {
      description = "Bootstrap Vault client environment for LuxNix system services";
      wantedBy = [ "multi-user.target" ];
      after = [ "local-fs.target" "systemd-tmpfiles-setup.service" ];
      requires = [ "systemd-tmpfiles-setup.service" ];
      wants = [ "local-fs.target" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "root";
        Group = "root";
        UMask = "0077";
        ExecStart = vaultAuthSetupScript;
        ExecStop = vaultAuthCleanupScript;
        EnvironmentFile = lib.optionals (cfg.client.environmentFile != null) [
          (toString cfg.client.environmentFile)
        ];
      };
      path = [
        pkgs.coreutils
        pkgs.vault
      ];
    };
  };
}
