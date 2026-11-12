# Client side of hub enrollment: CA trust, enrollment install and certificates.
{
  lib,
  pkgs,
  config,
  ctx,
  ...
}:
with lib;
with lib.luxnix;
let
  inherit (ctx)
    vaultCli
    cfg
    runtimeDir
    runtimeEnvironmentFile
    runtimeStatusFile
    clientReissueMarker
    verifySecretStorage
    verifyClientStorage
    clientHubPkiCfg
    vaultAuthErrorClassifierTool
    hubSecretStateDir
    ;
  sensitiveGroup = config.luxnix.generic-settings.sensitiveServiceGroupName;
  hubSecretHelper = ../../../../../scripts/vault/fetch_hub_secret.py;
  # Arguments shared by every hub KV fetch on this host.
  hubSecretHelperCommand = lib.escapeShellArgs (
    [
      "${pkgs.python3}/bin/python3"
      "-I"
      (toString hubSecretHelper)
      "--state-dir"
      hubSecretStateDir
      "--cli"
      "${vaultCli}/bin/vault"
      "--classifier"
      "${vaultAuthErrorClassifierTool}/bin/luxnix-vault-classify-auth-error"
    ]
    # allowOffline is the single outage switch: a hub outage keeps the last
    # accepted value; a wrong or stale answer is never papered over.
    ++ lib.optional cfg.client.allowOffline "--tolerate-outage"
  );
  hubSecretHelperArgs =
    {
      name,
      kvPath,
      field,
      stripNewlines ? false,
      emptyWhenUnavailable ? false,
    }:
    hubSecretHelperCommand
    + " "
    + lib.escapeShellArgs (
      [
        "--name"
        name
        "--kv-path"
        "${clientHubPkiCfg.kvMountPath}/${kvPath}"
        "--field"
        field
      ]
      ++ lib.optional stripNewlines "--strip-newlines"
      ++ lib.optional emptyWhenUnavailable "--empty-when-unavailable"
    );
  # managed-secrets generator body: fills $TARGET_FILE, $SECRET_FILE is the deployed copy.
  hubSecretFetch =
    args: ''${hubSecretHelperArgs args} --target "$TARGET_FILE" --previous "$SECRET_FILE"'';

  hubSecretsDeliverScript = pkgs.writeShellScript "luxnix-hub-secrets-deliver" ''
    set -euo pipefail
    umask 077
    ulimit -c 0

    ${verifyClientStorage}
    unset VAULT_SKIP_VERIFY VAULT_TLS_SERVER_NAME VAULT_AGENT_ADDR VAULT_TOKEN
    ${optionalString (cfg.client.address != null) ''
      export VAULT_ADDR=${lib.escapeShellArg cfg.client.address}
    ''}
    ${optionalString (cfg.client.caCertFile != null) ''
      export VAULT_CACERT=${lib.escapeShellArg (toString cfg.client.caCertFile)}
    ''}

    # Every run authenticates afresh: the boot-time token expires long before the next refresh.
    ${optionalString (cfg.client.auth.method == "approle") ''
      ROLE_ID_FILE=${lib.escapeShellArg (toString cfg.client.auth.roleIdFile)}
      SECRET_ID_FILE=${lib.escapeShellArg (toString cfg.client.auth.secretIdFile)}
      ${optionalString cfg.client.auth.deferUntilProvisioned ''
        if [ ! -s "$ROLE_ID_FILE" ] || [ ! -s "$SECRET_ID_FILE" ]; then
          echo "Hub enrollment is pending; no hub secrets are fetched yet."
          exit 0
        fi
      ''}
      VAULT_AUTH_ERROR_CLASSIFIER=${vaultAuthErrorClassifierTool}/bin/luxnix-vault-classify-auth-error
      source ${../../../../../scripts/vault/refresh-client-auth.sh}
      if ! refresh_client_auth; then
        case "''${VAULT_AUTH_STATE:-}" in
          vault-unreachable|vault-sealed) ;;
          *) echo "ERROR: the hub rejected this host; deployed secrets are left untouched." >&2; exit 1 ;;
        esac
      fi
    ''}
    ${optionalString (cfg.client.auth.method == "tokenFile") ''
      TOKEN_FILE=${lib.escapeShellArg (toString cfg.client.auth.tokenFile)}
      ${optionalString cfg.client.auth.deferUntilProvisioned ''
        if [ ! -s "$TOKEN_FILE" ]; then
          echo "Hub enrollment is pending; no hub secrets are fetched yet."
          exit 0
        fi
      ''}
      if [ ! -s "$TOKEN_FILE" ]; then
        echo "ERROR: the hub token file is missing or empty." >&2
        exit 1
      fi
      VAULT_TOKEN="$(tr -d '\n' < "$TOKEN_FILE")"
      export VAULT_TOKEN
      # Periodic site tokens live only while they are renewed.
      vault token renew >/dev/null 2>&1 \
        || echo "WARNING: the hub token was not renewed (hub unavailable or token not renewable)." >&2
    ''}

    failed=0
    deliver() {
      local name="$1" kv_path="$2" field="$3" path="$4" owner="$5" group="$6" mode="$7"
      local strip="$8" required="$9"
      shift 9
      local directory temporary
      local -a flags=()
      [ "$strip" = 1 ] && flags+=(--strip-newlines)
      [ "$required" = 1 ] || flags+=(--empty-when-unavailable)
      directory="$(dirname "$path")"
      [ -d "$directory" ] || install -d -m 0750 -o root -g ${lib.escapeShellArg sensitiveGroup} "$directory"
      ${verifySecretStorage} "$path"
      temporary="$(mktemp "$directory/.$name.tmp.XXXXXX")"
      if ! ${hubSecretHelperCommand} --name "$name" --kv-path "$kv_path" --field "$field" \
        --target "$temporary" --previous "$path" "''${flags[@]}"; then
        rm -f -- "$temporary"
        failed=1
        return 0
      fi
      if [ ! -s "$temporary" ]; then
        rm -f -- "$temporary"
        return 0
      fi
      chown "$owner:$group" "$temporary"
      chmod "$mode" "$temporary"
      if [ -f "$path" ] && cmp -s "$temporary" "$path"; then
        rm -f -- "$temporary"
        chown "$owner:$group" "$path"
        chmod "$mode" "$path"
        return 0
      fi
      mv -f -- "$temporary" "$path"
      echo "Deployed hub secret $name."
      for unit in "$@"; do
        systemctl try-restart --no-block "$unit"
      done
    }

    ${lib.concatStringsSep "\n" (
      lib.mapAttrsToList (
        name: secret:
        "deliver "
        + lib.escapeShellArgs (
          [
            name
            "${clientHubPkiCfg.kvMountPath}/${secret.kvPath}"
            secret.field
            secret.path
            secret.owner
            secret.group
            secret.mode
            (if secret.stripNewlines then "1" else "0")
            (if secret.required then "1" else "0")
          ]
          ++ secret.restartUnits
        )
      ) cfg.client.secrets
    )}
    exit "$failed"
  '';

  hubSecretsStatusTool = pkgs.writeShellApplication {
    name = "luxnix-hub-secrets-status";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.jq
    ];
    text = ''
      # Metadata only: names, KV paths, accepted versions and timestamps.
      shopt -s nullglob
      files=(${lib.escapeShellArg hubSecretStateDir}/*.json)
      if [ "''${#files[@]}" -eq 0 ]; then
        echo "No hub secret has been accepted on this host yet."
        exit 0
      fi
      for file in "''${files[@]}"; do
        jq -r --arg name "$(basename "$file" .json)" \
          '"\($name): \(.status // "unknown") version=\(.version // "none") path=\(.kv_path // "-") accepted=\((.accepted_at // 0) | todate) checked=\((.checked_at // 0) | todate)\(if .reason then " reason=" + .reason else "" end)"' \
          "$file"
      done
    '';
  };
  vaultCaInstallTool = pkgs.writeShellApplication {
    name = "luxnix-vault-install-server-ca";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.openssl
    ];
    text = ''
      set -euo pipefail
      umask 077
      ulimit -c 0
      if [ "$#" -ne 2 ]; then
        echo "Usage: luxnix-vault-install-server-ca <trusted-ca.pem> <expected-sha256-fingerprint>" >&2
        exit 2
      fi
      source_ca="$1"
      expected="$(${pkgs.coreutils}/bin/printf '%s' "$2" | ${pkgs.coreutils}/bin/tr -d ':[:space:]' | ${pkgs.coreutils}/bin/tr '[:lower:]' '[:upper:]')"
      actual="$(${pkgs.openssl}/bin/openssl x509 -in "$source_ca" -noout -fingerprint -sha256 \
        | ${pkgs.coreutils}/bin/cut -d= -f2 \
        | ${pkgs.coreutils}/bin/tr -d ':[:space:]' | ${pkgs.coreutils}/bin/tr '[:lower:]' '[:upper:]')"
      if [ -z "$expected" ] || [ "$actual" != "$expected" ]; then
        echo "ERROR: Vault CA fingerprint mismatch; refusing installation." >&2
        exit 1
      fi
      if ! ${pkgs.openssl}/bin/openssl x509 -in "$source_ca" -noout -text | grep -q 'CA:TRUE'; then
        echo "ERROR: supplied Vault trust anchor is not a CA certificate." >&2
        exit 1
      fi
      target=${lib.escapeShellArg (toString cfg.client.caCertFile)}
      target_dir="$(${pkgs.coreutils}/bin/dirname "$target")"
      ${pkgs.coreutils}/bin/install -d -m 0750 -o root \
        -g ${lib.escapeShellArg config.luxnix.generic-settings.sensitiveServiceGroupName} "$target_dir"
      temporary="$(${pkgs.coreutils}/bin/mktemp "$target_dir/.vault-server-ca.XXXXXX")"
      trap '${pkgs.coreutils}/bin/rm -f "$temporary"' EXIT
      ${pkgs.coreutils}/bin/install -m 0644 -o root -g root "$source_ca" "$temporary"
      ${pkgs.coreutils}/bin/mv -f "$temporary" "$target"
      trap - EXIT
      echo "Installed authenticated Vault CA with SHA-256 fingerprint $actual."
      echo "No service was restarted. Verify configuration, then start vault-auth-setup.service explicitly."
    '';
  };

  siteTokenInstallTool = pkgs.writeShellApplication {
    name = "luxnix-vault-install-site-token";
    runtimeInputs = [
      vaultCaInstallTool
      pkgs.coreutils
    ];
    text = ''
      set -euo pipefail
      umask 077
      ulimit -c 0

      if [ "$#" -ne 2 ]; then
        echo "Usage: luxnix-vault-install-site-token <token-directory> <expected-server-ca-sha256-fingerprint>" >&2
        exit 2
      fi
      if [ "$(id -u)" -ne 0 ]; then
        echo "ERROR: token installation must run as root." >&2
        exit 1
      fi
      source_directory="$1"
      ${verifyClientStorage}
      ${verifySecretStorage} "$source_directory"
      for name in site-token vault-server-ca.pem; do
        if [ -L "$source_directory/$name" ] || [ ! -f "$source_directory/$name" ] || [ ! -s "$source_directory/$name" ]; then
          echo "ERROR: token directory needs a non-empty regular file: $name" >&2
          exit 1
        fi
      done
      # The pinned CA is authenticated first; a token is useless against another server.
      luxnix-vault-install-server-ca "$source_directory/vault-server-ca.pem" "$2" >/dev/null

      target=${lib.escapeShellArg (toString cfg.client.auth.tokenFile)}
      target_directory="$(dirname "$target")"
      install -d -m 0750 -o root -g ${lib.escapeShellArg sensitiveGroup} "$target_directory"
      temporary="$(mktemp "$target_directory/.site-token.XXXXXX")"
      trap 'rm -f -- "$temporary"' EXIT
      install -m 0400 -o root -g root "$source_directory/site-token" "$temporary"
      mv -f -- "$temporary" "$target"
      trap - EXIT
      echo "Installed the authenticated server CA and this host's hub token."
      echo "No service was started. Start vault-auth-setup.service, then luxnix-hub-secrets.service."
    '';
  };

  hubSiteEnrollmentInstallTool = pkgs.writeShellApplication {
    name = "luxnix-vault-install-hub-site-enrollment";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.openssl
    ];
    text = ''
      set -euo pipefail
      umask 077
      ulimit -c 0

      if [ "$#" -ne 2 ]; then
        echo "Usage: luxnix-vault-install-hub-site-enrollment <enrollment-directory> <expected-vault-ca-sha256-fingerprint>" >&2
        exit 2
      fi
      if [ "$(${pkgs.coreutils}/bin/id -u)" -ne 0 ]; then
        echo "ERROR: enrollment installation must run as root." >&2
        exit 1
      fi

      source_directory="$1"
      ${verifyClientStorage}
      ${verifySecretStorage} "$source_directory"
      if [ -L "$source_directory" ] || [ ! -d "$source_directory" ]; then
        echo "ERROR: enrollment source must be a non-symlink directory." >&2
        exit 1
      fi

      validate_source() {
        local source_file="$source_directory/$1"
        if [ -L "$source_file" ] || [ ! -f "$source_file" ] || [ ! -s "$source_file" ]; then
          echo "ERROR: enrollment file must be a non-empty regular non-symlink file: $1" >&2
          exit 1
        fi
      }
      validate_source approle_role_id
      validate_source approle_secret_id
      validate_source vault-server-ca.pem
      validate_source source-node-secret

      expected="$(${pkgs.coreutils}/bin/printf '%s' "$2" \
        | ${pkgs.coreutils}/bin/tr -d ':[:space:]' \
        | ${pkgs.coreutils}/bin/tr '[:lower:]' '[:upper:]')"
      if ! ${pkgs.gnugrep}/bin/grep -Eq '^[0-9A-F]{64}$' <<< "$expected"; then
        echo "ERROR: expected Vault CA fingerprint must contain exactly 64 hexadecimal digits." >&2
        exit 2
      fi
      actual="$(${pkgs.openssl}/bin/openssl x509 \
        -in "$source_directory/vault-server-ca.pem" -noout -fingerprint -sha256 \
        | ${pkgs.coreutils}/bin/cut -d= -f2 \
        | ${pkgs.coreutils}/bin/tr -d ':[:space:]' \
        | ${pkgs.coreutils}/bin/tr '[:lower:]' '[:upper:]')"
      if [ "$actual" != "$expected" ]; then
        echo "ERROR: Vault CA fingerprint mismatch; refusing enrollment installation." >&2
        exit 1
      fi
      if ! ${pkgs.openssl}/bin/openssl x509 \
        -in "$source_directory/vault-server-ca.pem" -noout -text \
        | ${pkgs.gnugrep}/bin/grep -q 'CA:TRUE'; then
        echo "ERROR: supplied Vault trust anchor is not a CA certificate." >&2
        exit 1
      fi

      target_directory=${lib.escapeShellArg (builtins.dirOf clientHubPkiCfg.nodeSecretFile)}
      ${pkgs.coreutils}/bin/install -d -m 0750 -o root \
        -g ${lib.escapeShellArg config.luxnix.generic-settings.sensitiveServiceGroupName} \
        "$target_directory"

      temporary=""
      cleanup() {
        if [ -n "$temporary" ]; then
          ${pkgs.coreutils}/bin/rm -f -- "$temporary"
        fi
      }
      trap cleanup EXIT

      install_enrollment_file() {
        local source_name="$1"
        local target="$2"
        local mode="$3"
        local group="$4"
        temporary="$(${pkgs.coreutils}/bin/mktemp "$target_directory/.hub-site-enrollment.XXXXXX")"
        ${pkgs.coreutils}/bin/install -m "$mode" -o root -g "$group" \
          "$source_directory/$source_name" "$temporary"
        ${pkgs.coreutils}/bin/mv -f -- "$temporary" "$target"
        temporary=""
      }

      install_enrollment_file approle_role_id \
        ${lib.escapeShellArg (toString cfg.client.auth.roleIdFile)} 0400 root
      install_enrollment_file approle_secret_id \
        ${lib.escapeShellArg (toString cfg.client.auth.secretIdFile)} 0400 root
      install_enrollment_file vault-server-ca.pem \
        ${lib.escapeShellArg (toString cfg.client.caCertFile)} 0644 root
      install_enrollment_file source-node-secret \
        ${lib.escapeShellArg clientHubPkiCfg.nodeSecretFile} 0640 \
        ${lib.escapeShellArg config.luxnix.generic-settings.sensitiveServiceGroupName}
      trap - EXIT

      echo "Installed the authenticated hub-site enrollment bundle with protected service access."
      echo "No service was started. Run luxnix-vault-enrollment-status before starting the enrollment chain."
    '';
  };

  forceHubClientReissueTool = pkgs.writeShellApplication {
    name = "luxnix-vault-reissue-hub-client-certificate";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.systemd
    ];
    text = ''
      if [ "$#" -ne 0 ] || [ "$(id -u)" -ne 0 ]; then
        echo "Run as root on the explicitly selected site without arguments." >&2
        exit 2
      fi
      install -d -m 0700 ${lib.escapeShellArg runtimeDir}
      touch ${lib.escapeShellArg clientReissueMarker}
      chmod 0600 ${lib.escapeShellArg clientReissueMarker}
      systemctl restart luxnix-vault-issue-hub-client-certificate.service
      if [ -e ${lib.escapeShellArg clientReissueMarker} ]; then
        echo "ERROR: forced certificate replacement is incomplete; retain containment." >&2
        exit 1
      fi
      echo "A replacement certificate was published; verify receiver acceptance before restoring transfer access."
    '';
  };

  issueHubClientCertificateScript = pkgs.writeShellScript "issue-lx-hub-client-certificate" ''
    set -euo pipefail
    umask 077
    ulimit -c 0

    ${verifyClientStorage}
    ${verifySecretStorage} ${
      lib.escapeShellArgs [
        clientHubPkiCfg.certificateFile
        clientHubPkiCfg.keyFile
      ]
    }
    unset VAULT_SKIP_VERIFY VAULT_TLS_SERVER_NAME VAULT_AGENT_ADDR
    certificate=${lib.escapeShellArg clientHubPkiCfg.certificateFile}
    private_key=${lib.escapeShellArg clientHubPkiCfg.keyFile}
    client_ca=${lib.escapeShellArg clientHubPkiCfg.caCertificateFile}
    output_directory="$(${pkgs.coreutils}/bin/dirname "$certificate")"
    ${pkgs.coreutils}/bin/install -d -m 0750 -o root \
      -g ${lib.escapeShellArg config.luxnix.generic-settings.sensitiveServiceGroupName} \
      "$output_directory"

    certificate_matches_key() {
      certificate_public="$(${pkgs.openssl}/bin/openssl x509 -in "$certificate" -pubkey -noout \
        | ${pkgs.openssl}/bin/openssl pkey -pubin -outform DER \
        | ${pkgs.coreutils}/bin/sha256sum)" || return 1
      key_public="$(${pkgs.openssl}/bin/openssl pkey -in "$private_key" -pubout -outform DER \
        | ${pkgs.coreutils}/bin/sha256sum)" || return 1
      [ "$certificate_public" = "$key_public" ]
    }

    force_reissue=0
    if [ -e ${lib.escapeShellArg clientReissueMarker} ]; then
      force_reissue=1
    fi

    if [ "$force_reissue" = 0 ] && [ -s "$certificate" ] && [ -s "$private_key" ] \
      && ${pkgs.openssl}/bin/openssl x509 -in "$certificate" -noout \
        -checkend ${toString clientHubPkiCfg.renewBeforeSeconds} \
      && certificate_matches_key; then
      exit 0
    fi

    ${optionalString (cfg.client.auth.method == "approle") ''
      export PATH=${
        lib.makeBinPath [
          pkgs.jq
          vaultCli
        ]
      }:"$PATH"
      ${optionalString (cfg.client.address != null) ''
        export VAULT_ADDR=${lib.escapeShellArg cfg.client.address}
      ''}
      ${optionalString (cfg.client.caCertFile != null) ''
        export VAULT_CACERT=${lib.escapeShellArg (toString cfg.client.caCertFile)}
      ''}
      ROLE_ID_FILE=${lib.escapeShellArg (toString cfg.client.auth.roleIdFile)}
      SECRET_ID_FILE=${lib.escapeShellArg (toString cfg.client.auth.secretIdFile)}
      VAULT_AUTH_ERROR_CLASSIFIER=${vaultAuthErrorClassifierTool}/bin/luxnix-vault-classify-auth-error
      source ${../../../../../scripts/vault/refresh-client-auth.sh}
      if ! refresh_client_auth; then
        ${optionalString cfg.client.allowOffline ''
          if [ "$force_reissue" = 0 ] && [ -s "$certificate" ] && [ -s "$client_ca" ] \
            && ${pkgs.openssl}/bin/openssl x509 -in "$certificate" -noout -checkend 0 \
            && certificate_matches_key; then
            echo "WARNING: fresh authentication unavailable; retaining still-valid cached certificate." >&2
            exit 0
          fi
        ''}
        exit 1
      fi
    ''}

    if [ ! -s ${lib.escapeShellArg runtimeEnvironmentFile} ] && [ -z "''${VAULT_TOKEN:-}" ]; then
      state="enrollment-pending"
      if [ -s ${lib.escapeShellArg runtimeStatusFile} ]; then
        state="$(${pkgs.coreutils}/bin/cat ${lib.escapeShellArg runtimeStatusFile})"
      fi
      ${optionalString cfg.client.allowOffline ''
        if [ "$force_reissue" = 0 ] && [ -s "$certificate" ] && [ -s "$private_key" ] && [ -s "$client_ca" ]; then
          echo "WARNING: Vault runtime credentials are unavailable (state: $state); retaining cached hub PKI files." >&2
          exit 0
        fi
      ''}
      echo "ERROR: Vault runtime credentials are unavailable (state: $state); client certificate issuance remains fail-closed." >&2
      echo "Run luxnix-vault-enrollment-status for recovery guidance." >&2
      exit 1
    fi

    response="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.issue-response.XXXXXX")"
    cert_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.client-cert.XXXXXX")"
    key_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.client-key.XXXXXX")"
    ca_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.client-ca.XXXXXX")"
    cleanup() {
      ${pkgs.coreutils}/bin/rm -f "$response" "$cert_tmp" "$key_tmp" "$ca_tmp"
    }
    trap cleanup EXIT

    if ! ${vaultCli}/bin/vault write -format=json \
      ${lib.escapeShellArg "${clientHubPkiCfg.mountPath}/issue/${clientHubPkiCfg.roleName}"} \
      common_name=${lib.escapeShellArg clientHubPkiCfg.commonName} \
      ttl=${lib.escapeShellArg clientHubPkiCfg.ttl} > "$response"; then
      ${optionalString cfg.client.allowOffline ''
        if [ "$force_reissue" = 0 ] && [ -s "$certificate" ] && [ -s "$private_key" ] && [ -s "$client_ca" ]; then
          echo "WARNING: Vault certificate renewal failed; continuing with cached hub PKI files." >&2
          exit 0
        fi
      ''}
      echo "ERROR: Vault client certificate issuance failed." >&2
      exit 1
    fi
    ${pkgs.jq}/bin/jq -er '.data.certificate' "$response" > "$cert_tmp"
    ${pkgs.jq}/bin/jq -er '.data.private_key' "$response" > "$key_tmp"
    ${pkgs.jq}/bin/jq -er '.data.issuing_ca' "$response" > "$ca_tmp"

    ${pkgs.openssl}/bin/openssl x509 -in "$cert_tmp" -noout -checkend 86400
    cert_public="$(${pkgs.openssl}/bin/openssl x509 -in "$cert_tmp" -pubkey -noout \
      | ${pkgs.openssl}/bin/openssl pkey -pubin -outform DER \
      | ${pkgs.coreutils}/bin/sha256sum)"
    key_public="$(${pkgs.openssl}/bin/openssl pkey -in "$key_tmp" -pubout -outform DER \
      | ${pkgs.coreutils}/bin/sha256sum)"
    if [ "$cert_public" != "$key_public" ]; then
      echo "Vault returned a client certificate and private key that do not match." >&2
      exit 1
    fi

    ${pkgs.coreutils}/bin/chown root:${lib.escapeShellArg config.luxnix.generic-settings.sensitiveServiceGroupName} \
      "$cert_tmp" "$key_tmp" "$ca_tmp"
    ${pkgs.coreutils}/bin/chmod 0640 "$cert_tmp" "$ca_tmp"
    ${pkgs.coreutils}/bin/chmod 0640 "$key_tmp"
    ${pkgs.coreutils}/bin/mv -f "$cert_tmp" "$certificate"
    ${pkgs.coreutils}/bin/mv -f "$key_tmp" "$private_key"
    ${pkgs.coreutils}/bin/mv -f "$ca_tmp" "$client_ca"
    ${pkgs.coreutils}/bin/rm -f "$response" ${lib.escapeShellArg clientReissueMarker}
    trap - EXIT
  '';
in
{
  inherit
    siteTokenInstallTool
    hubSecretFetch
    hubSecretsDeliverScript
    hubSecretsStatusTool
    vaultCaInstallTool
    hubSiteEnrollmentInstallTool
    forceHubClientReissueTool
    issueHubClientCertificateScript
    ;
}
