# Hub PKI bootstrap and publication of the hub client CA.
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
    verifySecretStorage
    serverCfg
    hubPkiCfg
    ;

  hubPkiBootstrapTool = pkgs.writeShellApplication {
    name = "luxnix-vault-bootstrap-hub-pki";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.jq
      pkgs.openssl
      pkgs.vault
    ];
    text = ''
      set -euo pipefail
      umask 077
      ulimit -c 0

      if [ -z "''${VAULT_ADDR:-}" ] || [ -z "''${VAULT_TOKEN:-}" ]; then
        echo "VAULT_ADDR and a short-lived administrative VAULT_TOKEN are required." >&2
        exit 1
      fi

      if ! vault status >/dev/null; then
        echo "Vault must be initialized and unsealed before PKI bootstrap." >&2
        exit 1
      fi

      mount=${lib.escapeShellArg hubPkiCfg.mountPath}
      kv_mount=${lib.escapeShellArg hubPkiCfg.kvMountPath}
      role=${lib.escapeShellArg hubPkiCfg.clientRoleName}
      max_ttl=${lib.escapeShellArg hubPkiCfg.maxTtl}
      client_ttl=${lib.escapeShellArg hubPkiCfg.clientTtl}
      recipient_public_key=${lib.escapeShellArg hubPkiCfg.recipientPublicKeyFile}
      recipient_public_key_kv_path=${lib.escapeShellArg hubPkiCfg.recipientPublicKeyKvPath}
      recipient_private_key="''${recipient_public_key%.pub.pem}.pem"
      recipient_sensitive_group=${lib.escapeShellArg config.luxnix.generic-settings.sensitiveServiceGroupName}
      recipient_private_dir="$(${pkgs.coreutils}/bin/dirname "$recipient_private_key")"
      recipient_public_dir="$(${pkgs.coreutils}/bin/dirname "$recipient_public_key")"
      published_json="$(${pkgs.coreutils}/bin/mktemp)"
      published_error="$(${pkgs.coreutils}/bin/mktemp)"
      published_public_key="$(${pkgs.coreutils}/bin/mktemp)"
      secrets_json=""
      private_tmp=""
      public_tmp=""

      cleanup() {
        ${pkgs.coreutils}/bin/rm -f \
          "$published_json" \
          "$published_error" \
          "$published_public_key"
        if [ -n "$secrets_json" ]; then
          ${pkgs.coreutils}/bin/rm -f "$secrets_json"
        fi
        if [ -n "$private_tmp" ]; then
          ${pkgs.coreutils}/bin/rm -f "$private_tmp"
        fi
        if [ -n "$public_tmp" ]; then
          ${pkgs.coreutils}/bin/rm -f "$public_tmp"
        fi
      }
      trap cleanup EXIT

      if [ "$recipient_private_key" = "$recipient_public_key" ]; then
        recipient_private_key="$recipient_public_key.pem"
        recipient_private_dir="$(${pkgs.coreutils}/bin/dirname "$recipient_private_key")"
      fi

      validate_existing_path() {
        local path="$1"
        local label="$2"
        if [ -e "$path" ] || [ -L "$path" ]; then
          if [ -L "$path" ] || [ ! -f "$path" ] || [ ! -s "$path" ]; then
            echo "ERROR: $label must be a non-empty regular non-symlink file: $path" >&2
            exit 1
          fi
        fi
      }

      validate_private_key() {
        local path="$1"
        ${pkgs.openssl}/bin/openssl pkey -in "$path" -check -noout >/dev/null 2>&1 \
          && ${pkgs.openssl}/bin/openssl pkey -in "$path" -text -noout 2>/dev/null \
            | ${pkgs.gnugrep}/bin/grep -q X25519
      }

      validate_public_key() {
        local path="$1"
        ${pkgs.openssl}/bin/openssl pkey -pubin -in "$path" -text_pub -noout 2>/dev/null \
          | ${pkgs.gnugrep}/bin/grep -q X25519
      }

      private_public_fingerprint() {
        local path="$1"
        ${pkgs.openssl}/bin/openssl pkey -in "$path" -pubout -outform DER 2>/dev/null \
          | ${pkgs.coreutils}/bin/sha256sum \
          | ${pkgs.coreutils}/bin/cut -d ' ' -f1
      }

      public_fingerprint() {
        local path="$1"
        ${pkgs.openssl}/bin/openssl pkey -pubin -in "$path" -outform DER 2>/dev/null \
          | ${pkgs.coreutils}/bin/sha256sum \
          | ${pkgs.coreutils}/bin/cut -d ' ' -f1
      }

      read_published_public_key() {
        : > "$published_json"
        : > "$published_error"
        : > "$published_public_key"

        if vault kv get -format=json "$kv_mount/$recipient_public_key_kv_path" \
          > "$published_json" 2> "$published_error"; then
          if ! ${pkgs.jq}/bin/jq -er '.data.data.public_key' "$published_json" \
            > "$published_public_key"; then
            echo "ERROR: Vault recipient-key record does not contain a non-empty public_key field." >&2
            return 1
          fi
          if ! ${pkgs.jq}/bin/jq -er '.data.metadata.version | numbers' "$published_json" >/dev/null; then
            echo "ERROR: Vault recipient-key record does not expose a KV v2 version." >&2
            return 1
          fi
          return 0
        fi

        if ${pkgs.gnugrep}/bin/grep -Fq 'No value found at' "$published_error"; then
          return 3
        fi

        echo "ERROR: failed to read the published hub recipient key; refusing to treat the Vault error as an absent key." >&2
        return 1
      }

      ${verifySecretStorage} "$recipient_private_dir" "$recipient_public_dir"
      ${pkgs.coreutils}/bin/install -d -m 0750 -o root -g "$recipient_sensitive_group" \
        "$recipient_private_dir" "$recipient_public_dir"

      validate_existing_path "$recipient_private_key" "hub envelope recipient private key"
      validate_existing_path "$recipient_public_key" "hub envelope recipient public key"

      secrets_json="$(${pkgs.coreutils}/bin/mktemp)"
      if ! vault secrets list -format=json > "$secrets_json"; then
        ${pkgs.coreutils}/bin/rm -f "$secrets_json"
        echo "ERROR: unable to inspect Vault secrets engines." >&2
        exit 1
      fi
      if ! ${pkgs.jq}/bin/jq -e --arg path "$mount/" 'has($path)' "$secrets_json" >/dev/null; then
        vault secrets enable -path="$mount" pki
      fi
      if ! ${pkgs.jq}/bin/jq -e --arg path "$kv_mount/" 'has($path)' "$secrets_json" >/dev/null; then
        vault secrets enable -path="$kv_mount" -version=2 kv
      fi
      ${pkgs.coreutils}/bin/rm -f "$secrets_json"
      secrets_json=""
      vault secrets tune -max-lease-ttl="$max_ttl" "$mount"

      published_state=missing
      published_version=""
      if read_published_public_key; then
        published_state=present
        published_version="$(${pkgs.jq}/bin/jq -er '.data.metadata.version' "$published_json")"
        if ! validate_public_key "$published_public_key"; then
          echo "ERROR: Vault contains an invalid central-hub X25519 recipient public key." >&2
          exit 1
        fi
      else
        read_status="$?"
        if [ "$read_status" -ne 3 ]; then
          exit "$read_status"
        fi
      fi

      recipient_priv_state=missing
      recipient_pub_state=missing
      if [ -f "$recipient_private_key" ] && [ -s "$recipient_private_key" ]; then
        recipient_priv_state=present
      fi
      if [ -f "$recipient_public_key" ] && [ -s "$recipient_public_key" ]; then
        recipient_pub_state=present
      fi

      if [ "$recipient_priv_state" = "missing" ]; then
        if [ "$recipient_pub_state" = "present" ]; then
          echo "ERROR: hub envelope recipient public key exists without its matching private key: $recipient_public_key" >&2
          echo "Restore the matching private key; never regenerate it implicitly." >&2
          exit 1
        fi
        if [ "$published_state" = "present" ]; then
          echo "ERROR: Vault already publishes a hub recipient identity, but the matching local private key is absent." >&2
          echo "Restore the matching private key from the approved backup; refusing to create an unrelated identity." >&2
          exit 1
        fi

        echo "No local or published hub envelope recipient identity exists; generating a fresh X25519 key pair." >&2
        private_tmp="$(${pkgs.coreutils}/bin/mktemp "$recipient_private_dir/.hub-recipient-private.XXXXXX")"
        public_tmp="$(${pkgs.coreutils}/bin/mktemp "$recipient_public_dir/.hub-recipient-public.XXXXXX")"

        ${pkgs.openssl}/bin/openssl genpkey -algorithm X25519 -out "$private_tmp"
        ${pkgs.openssl}/bin/openssl pkey -in "$private_tmp" -pubout > "$public_tmp"
        if ! validate_private_key "$private_tmp" || ! validate_public_key "$public_tmp"; then
          echo "ERROR: generated hub recipient key pair failed X25519 validation." >&2
          exit 1
        fi

        ${pkgs.coreutils}/bin/chown "root:$recipient_sensitive_group" "$private_tmp" "$public_tmp"
        ${pkgs.coreutils}/bin/chmod 0640 "$private_tmp" "$public_tmp"
        # Publish the private half first. If interrupted before the public move,
        # the next run can safely derive the public half from the private key.
        ${pkgs.coreutils}/bin/mv -f "$private_tmp" "$recipient_private_key"
        private_tmp=""
        ${pkgs.coreutils}/bin/mv -f "$public_tmp" "$recipient_public_key"
        public_tmp=""
        recipient_priv_state=present
        recipient_pub_state=present
      fi

      if ! validate_private_key "$recipient_private_key"; then
        echo "ERROR: hub envelope recipient private key validation failed: $recipient_private_key" >&2
        exit 1
      fi

      if [ "$recipient_pub_state" = "missing" ]; then
        echo "Deriving missing hub recipient public key from the existing private key." >&2
        public_tmp="$(${pkgs.coreutils}/bin/mktemp "$recipient_public_dir/.hub-recipient-public.XXXXXX")"
        ${pkgs.openssl}/bin/openssl pkey -in "$recipient_private_key" -pubout > "$public_tmp"
        if ! validate_public_key "$public_tmp"; then
          echo "ERROR: failed to derive a valid X25519 public key from $recipient_private_key" >&2
          exit 1
        fi
        ${pkgs.coreutils}/bin/chown "root:$recipient_sensitive_group" "$public_tmp"
        ${pkgs.coreutils}/bin/chmod 0640 "$public_tmp"
        ${pkgs.coreutils}/bin/mv -f "$public_tmp" "$recipient_public_key"
        public_tmp=""
      fi

      if ! validate_public_key "$recipient_public_key"; then
        echo "ERROR: hub envelope recipient public key validation failed: $recipient_public_key" >&2
        exit 1
      fi

      local_private_fingerprint="$(private_public_fingerprint "$recipient_private_key")"
      local_public_fingerprint="$(public_fingerprint "$recipient_public_key")"
      if [ "$local_private_fingerprint" != "$local_public_fingerprint" ]; then
        echo "ERROR: hub recipient public and private keys do not match." >&2
        exit 1
      fi

      ${pkgs.coreutils}/bin/chown "root:$recipient_sensitive_group" \
        "$recipient_private_key" "$recipient_public_key"
      ${pkgs.coreutils}/bin/chmod 0640 "$recipient_private_key" "$recipient_public_key"

      if [ "$published_state" = "present" ]; then
        published_fingerprint="$(public_fingerprint "$published_public_key")"
        if [ "$local_public_fingerprint" != "$published_fingerprint" ]; then
          if [ "''${LUXNIX_VAULT_ALLOW_HUB_RECIPIENT_ROTATION:-0}" != "1" ]; then
            echo "ERROR: Vault already contains a different hub recipient public key; refusing implicit rotation." >&2
            echo "Deploy the current-and-retiring private-key set, then rerun with LUXNIX_VAULT_ALLOW_HUB_RECIPIENT_ROTATION=1." >&2
            exit 1
          fi
          vault kv put -cas="$published_version" \
            "$kv_mount/$recipient_public_key_kv_path" public_key=- \
            < "$recipient_public_key" >/dev/null
        fi
      else
        vault kv put -cas=0 "$kv_mount/$recipient_public_key_kv_path" public_key=- \
          < "$recipient_public_key" >/dev/null
      fi

      if ! vault read "$mount/cert/ca" >/dev/null 2>&1; then
        vault write "$mount/root/generate/internal" \
          common_name=${lib.escapeShellArg hubPkiCfg.caCommonName} \
          ttl="$max_ttl" >/dev/null
      fi

      vault write "$mount/roles/$role" \
        allowed_domains=${lib.escapeShellArg hubPkiCfg.allowedDnsSuffix} \
        allow_subdomains=true \
        allow_bare_domains=false \
        enforce_hostnames=true \
        client_flag=true \
        server_flag=false \
        key_type=ec \
        key_bits=256 \
        max_ttl="$client_ttl" >/dev/null

      trap - EXIT
      cleanup
      echo "Vault hub-transfer PKI is ready at $mount with role $role."
    '';
  };

  publishHubClientCaScript = pkgs.writeShellScript "publish-lx-hub-client-ca" ''
    set -euo pipefail
    umask 027

    destination=${lib.escapeShellArg hubPkiCfg.caCertificateFile}
    destination_dir="$(${pkgs.coreutils}/bin/dirname "$destination")"
    ${pkgs.coreutils}/bin/install -d -m 0750 -o root \
      -g ${lib.escapeShellArg config.luxnix.generic-settings.sensitiveServiceGroupName} \
      "$destination_dir"
    temporary="$(${pkgs.coreutils}/bin/mktemp "$destination_dir/.hub-client-ca.XXXXXX")"
    trap '${pkgs.coreutils}/bin/rm -f "$temporary"' EXIT

    if ! ${pkgs.coreutils}/bin/timeout 30s ${pkgs.bash}/bin/bash -c '
      curl_bin="$1"
      ca_cert="$2"
      health_url="$3"

      cmd=("$curl_bin" --fail --silent --show-error --connect-timeout 2 --max-time 5 --proto =https --tlsv1.2)
      if [[ -n "$ca_cert" ]]; then
        cmd+=(--cacert "$ca_cert")
      fi

      for retry in $(seq 1 15); do
        if "''${cmd[@]}" "$health_url" >/dev/null 2>&1; then
          exit 0
        fi
        sleep 2
      done
      exit 1
    ' _ \
      "${pkgs.curl}/bin/curl" \
      "${lib.optionalString (serverCfg.caCertFile != null) (toString serverCfg.caCertFile)}" \
      "${serverCfg.apiAddress}/v1/sys/health"; then
      echo "Vault API at ${lib.escapeShellArg "${serverCfg.apiAddress}/v1/sys/health"} did not become reachable." >&2
      exit 1
    fi

    ${pkgs.curl}/bin/curl --fail --silent --show-error \
      --retry 30 --retry-delay 2 --retry-connrefused \
      --connect-timeout 2 --max-time 90 \
      --proto '=https' --tlsv1.2 \
      ${
        lib.optionalString (
          serverCfg.caCertFile != null
        ) "--cacert ${lib.escapeShellArg (toString serverCfg.caCertFile)}"
      } \
      ${lib.escapeShellArg "${serverCfg.apiAddress}/v1/${hubPkiCfg.mountPath}/ca/pem"} \
      > "$temporary"
    ${pkgs.openssl}/bin/openssl x509 -in "$temporary" -noout -checkend 86400
    ${pkgs.coreutils}/bin/chown root:${lib.escapeShellArg config.luxnix.generic-settings.sensitiveServiceGroupName} "$temporary"
    ${pkgs.coreutils}/bin/chmod 0640 "$temporary"
    ${pkgs.coreutils}/bin/mv -f "$temporary" "$destination"
    trap - EXIT
  '';
in
{
  inherit
    hubPkiBootstrapTool
    publishHubClientCaScript
    ;
}
