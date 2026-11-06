# Client authentication: token setup, provisioning gate, status and cleanup.
{
  lib,
  pkgs,
  ctx,
  ...
}:
with lib;
with lib.luxnix;
let
  inherit (ctx)
    cfg
    runtimeDir
    runtimeEnvironmentFile
    runtimeTokenFile
    runtimeStatusFile
    verifyClientStorage
    ;

  vaultAuthErrorClassifierTool = pkgs.writeShellApplication {
    name = "luxnix-vault-classify-auth-error";
    runtimeInputs = [ pkgs.gnugrep ];
    text = builtins.readFile ../../../../../scripts/vault/classify-auth-error.sh;
  };
  vaultAuthSetupScript = pkgs.writeShellScript "luxnix-vault-auth-setup" ''
    set -euo pipefail
    umask 077
    ulimit -c 0

    ${verifyClientStorage}
    unset VAULT_SKIP_VERIFY VAULT_TLS_SERVER_NAME VAULT_AGENT_ADDR
    RUNTIME_DIR="${runtimeDir}"
    TOKEN_FILE="${runtimeTokenFile}"
    ENV_FILE="${runtimeEnvironmentFile}"
    TMP_ENV="$(mktemp "$RUNTIME_DIR/.vault.env.XXXXXX")"
    TMP_TOKEN="$(mktemp "$RUNTIME_DIR/.vault.token.XXXXXX")"
    TMP_AUTH="$(mktemp "$RUNTIME_DIR/.vault-approle.XXXXXX")"
    trap 'rm -f "$TMP_ENV" "$TMP_TOKEN" "$TMP_AUTH"' EXIT

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
        if [ -z "$ROLE_ID" ] || [ -z "$SECRET_ID" ]; then
          echo "ERROR: Vault AppRole files must not be empty." >&2
          exit 1
        fi
        chmod 0600 "$TMP_AUTH"
        printf '%s\n%s\n' "$ROLE_ID" "$SECRET_ID" \
          | ${pkgs.jq}/bin/jq -Rn \
            '[inputs] as $credentials | { role_id: $credentials[0], secret_id: $credentials[1] }' \
            > "$TMP_AUTH"
        unset ROLE_ID SECRET_ID
        if ! ${pkgs.vault}/bin/vault write -field=token auth/approle/login @"$TMP_AUTH" > "$TMP_TOKEN"; then
          ${optionalString cfg.client.allowOffline ''
            echo "WARNING: Vault authentication failed; continuing with locally cached secrets." >&2
            exit 0
          ''}
          echo "ERROR: Vault AppRole authentication failed." >&2
          exit 1
        fi
        rm -f "$TMP_AUTH"
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
    rm -f "$TMP_AUTH"
    trap - EXIT
  '';

  vaultAuthProvisioningConditionScript = pkgs.writeShellScript "luxnix-vault-auth-provisioning-condition" ''
    set -euo pipefail

    ${verifyClientStorage}
    unset VAULT_SKIP_VERIFY VAULT_TLS_SERVER_NAME VAULT_AGENT_ADDR
    write_status() {
      status="$1"
      temporary="$(${pkgs.coreutils}/bin/mktemp ${lib.escapeShellArg runtimeDir}/.enrollment-status.XXXXXX)"
      ${pkgs.coreutils}/bin/printf '%s\n' "$status" > "$temporary"
      ${pkgs.coreutils}/bin/chmod 0644 "$temporary"
      ${pkgs.coreutils}/bin/mv -f "$temporary" ${lib.escapeShellArg runtimeStatusFile}
    }

    missing=0
    ${optionalString (cfg.client.auth.method == "approle") ''
      ROLE_ID_FILE=${lib.escapeShellArg (toString cfg.client.auth.roleIdFile)}
      SECRET_ID_FILE=${lib.escapeShellArg (toString cfg.client.auth.secretIdFile)}
      CA_CERT_FILE=${lib.escapeShellArg (toString cfg.client.caCertFile)}

      for required_file in "$ROLE_ID_FILE" "$SECRET_ID_FILE" "$CA_CERT_FILE"; do
        if [ ! -s "$required_file" ]; then
          echo "WARNING: vault-auth-setup is deferred; required enrollment file is missing or empty: $required_file" >&2
          missing=1
        fi
      done
    ''}

    if [ "$missing" -ne 0 ]; then
      rm -f ${lib.escapeShellArg runtimeEnvironmentFile} ${lib.escapeShellArg runtimeTokenFile}
      write_status enrollment-pending
      echo "WARNING: lx-annotate remains fail-closed until its Vault enrollment bundle is installed." >&2
      echo "After installing the bundle, run: systemctl start vault-auth-setup.service" >&2
      exit 1
    fi

    auth_error="$(${pkgs.coreutils}/bin/mktemp ${lib.escapeShellArg runtimeDir}/.vault-auth-error.XXXXXX)"
    trap '${pkgs.coreutils}/bin/rm -f "$auth_error"' EXIT
    # Only newly authenticated credentials may establish readiness.
    rm -f ${lib.escapeShellArg runtimeEnvironmentFile} ${lib.escapeShellArg runtimeTokenFile}
    if ! ${vaultAuthSetupScript} 2> "$auth_error"; then
      rm -f ${lib.escapeShellArg runtimeEnvironmentFile} ${lib.escapeShellArg runtimeTokenFile}
      auth_state="$(${vaultAuthErrorClassifierTool}/bin/luxnix-vault-classify-auth-error "$auth_error")"
      write_status "$auth_state"
      case "$auth_state" in
        tls-trust-failed)
          echo "ERROR: vault-auth-setup is deferred: TLS trust failed. The installed Vault CA does not authenticate the presented server leaf." >&2
          echo "Use the authenticated CA migration procedure; never enable VAULT_SKIP_VERIFY or fetch a CA from the unauthenticated endpoint." >&2
          ;;
        vault-sealed)
          echo "ERROR: vault-auth-setup is deferred: Vault is sealed." >&2
          echo "An authorized operator must unseal Vault on gs-02; clients never receive or use unseal keys." >&2
          ;;
        vault-unreachable)
          echo "ERROR: vault-auth-setup is deferred: Vault is unreachable through the configured network path." >&2
          ;;
        auth-rejected)
          echo "ERROR: vault-auth-setup is deferred: Vault rejected the supplied authentication material." >&2
          ;;
        *)
          echo "ERROR: vault-auth-setup is deferred because Vault authentication failed with an unclassified, non-secret error." >&2
          ;;
      esac
      echo "WARNING: lx-annotate remains fail-closed. Run luxnix-vault-enrollment-status for safe recovery guidance." >&2
      echo "After correcting the problem, run: systemctl start vault-auth-setup.service" >&2
      exit 1
    fi
    if [ -s ${lib.escapeShellArg runtimeEnvironmentFile} ]; then
      write_status ready
    else
      write_status offline-cached
      echo "WARNING: Vault authentication is unavailable; only explicitly allowed cached artifacts may continue." >&2
    fi
    ${pkgs.coreutils}/bin/rm -f "$auth_error"
    trap - EXIT
  '';

  vaultEnrollmentStatusTool = pkgs.writeShellApplication {
    name = "luxnix-vault-enrollment-status";
    runtimeInputs = [ pkgs.coreutils ];
    text = ''
      set -euo pipefail
      status_file=${lib.escapeShellArg runtimeStatusFile}
      if [ ! -s "$status_file" ]; then
        echo "Vault enrollment state: unknown (vault-auth-setup has not recorded a state)."
        exit 1
      fi
      state="$(cat "$status_file")"
      echo "Vault enrollment state: $state"
      case "$state" in
        ready) exit 0 ;;
        enrollment-pending)
          echo "Install the authenticated enrollment bundle, then start vault-auth-setup.service."
          ;;
        tls-trust-failed)
          echo "Install the stable server CA only after verifying its SHA-256 fingerprint from trusted gs-02 state."
          ;;
        vault-sealed)
          echo "An authorized operator must unseal Vault on gs-02. Do not place unseal keys on this client."
          ;;
        vault-unreachable)
          echo "Check the configured VPN/DNS route and Vault service availability; TLS verification remains mandatory."
          ;;
        auth-rejected)
          echo "Replace the AppRole enrollment files through the approved authenticated delivery channel."
          ;;
        vault-error)
          echo "Inspect: journalctl -u vault-auth-setup.service -b"
          ;;
        offline-cached)
          echo "Vault is not authenticated; only services with an explicit cached-artifact policy may continue."
          ;;
        *) echo "Inspect: journalctl -u vault-auth-setup.service -b" ;;
      esac
      exit 1
    '';
  };

  vaultAuthCleanupScript = pkgs.writeShellScript "luxnix-vault-auth-cleanup" ''
    set -euo pipefail
    rm -f ${lib.escapeShellArg runtimeEnvironmentFile} ${lib.escapeShellArg runtimeTokenFile} ${lib.escapeShellArg runtimeStatusFile}
  '';
in
{
  inherit
    vaultAuthErrorClassifierTool
    vaultAuthProvisioningConditionScript
    vaultEnrollmentStatusTool
    vaultAuthCleanupScript
    ;
}
