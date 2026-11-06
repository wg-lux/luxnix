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
    cfg
    runtimeDir
    runtimeEnvironmentFile
    runtimeStatusFile
    clientReissueMarker
    verifySecretStorage
    verifyClientStorage
    clientHubPkiCfg
    vaultAuthErrorClassifierTool
    ;
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
          pkgs.vault
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

    if ! ${pkgs.vault}/bin/vault write -format=json \
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
    vaultCaInstallTool
    hubSiteEnrollmentInstallTool
    forceHubClientReissueTool
    issueHubClientCertificateScript
    ;
}
