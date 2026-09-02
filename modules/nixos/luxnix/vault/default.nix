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
  runtimeStatusFile = "${runtimeDir}/enrollment-status";
  vaultAuthEnabled = cfg.enable && cfg.client.enable && cfg.client.auth.method != "none";
  serverCfg = cfg.server;
  managedTlsCfg = serverCfg.managedTls;
  hubPkiCfg = serverCfg.hubPki;
  clientHubPkiCfg = cfg.client.hubPki;

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

  hubSitesReconcileTool = pkgs.writeShellApplication {
    name = "luxnix-vault-reconcile-hub-sites";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.jq
      pkgs.vault
    ];
    text = ''
      set -euo pipefail
      umask 077

      if [ "$#" -lt 1 ]; then
        echo "Usage: luxnix-vault-reconcile-hub-sites <site-node-fqdn>..." >&2
        exit 2
      fi
      if [ -z "''${VAULT_ADDR:-}" ] || [ -z "''${VAULT_TOKEN:-}" ]; then
        echo "VAULT_ADDR and a short-lived administrative VAULT_TOKEN are required." >&2
        exit 1
      fi
      if ! vault status >/dev/null; then
        echo "Vault must be initialized and unsealed before site reconciliation." >&2
        exit 1
      fi

      mount=${lib.escapeShellArg hubPkiCfg.mountPath}
      kv_mount=${lib.escapeShellArg hubPkiCfg.kvMountPath}
      client_ttl=${lib.escapeShellArg hubPkiCfg.clientTtl}
      recipient_public_key_kv_path=${lib.escapeShellArg hubPkiCfg.recipientPublicKeyKvPath}
      policy_file=""
      state_file="$(${pkgs.coreutils}/bin/mktemp)"

      cleanup() {
        if [ -n "$policy_file" ]; then
          ${pkgs.coreutils}/bin/rm -f "$policy_file"
        fi
        ${pkgs.coreutils}/bin/rm -f "$state_file"
      }
      trap cleanup EXIT

      vault secrets list -format=json > "$state_file"
      if ! ${pkgs.jq}/bin/jq -e --arg path "$mount/" 'has($path)' "$state_file" >/dev/null \
        || ! ${pkgs.jq}/bin/jq -e --arg path "$kv_mount/" 'has($path)' "$state_file" >/dev/null; then
        echo "ERROR: hub PKI/KV mounts are absent; run luxnix-vault-bootstrap-hub-pki first." >&2
        exit 1
      fi

      vault auth list -format=json > "$state_file"
      if ! ${pkgs.jq}/bin/jq -e 'has("approle/")' "$state_file" >/dev/null; then
        vault auth enable approle >/dev/null
      fi

      reconcile_site() {
        local node_fqdn="$1"
        local role=""
        local policy=""

        case "$node_fqdn" in
          *[!A-Za-z0-9.-]*|.*|*..*|*.)
            echo "site-node-fqdn must be a valid DNS name: $node_fqdn" >&2
            return 2
            ;;
        esac

        role="site-$(${pkgs.coreutils}/bin/printf '%s' "$node_fqdn" | ${pkgs.coreutils}/bin/tr '.-' '__')"
        policy="lx-hub-$role"

        vault write "$mount/roles/$role" \
          allowed_domains="$node_fqdn" \
          allow_bare_domains=true \
          allow_subdomains=false \
          enforce_hostnames=true \
          client_flag=true \
          server_flag=false \
          key_type=ec \
          key_bits=256 \
          max_ttl="$client_ttl" >/dev/null

        policy_file="$(${pkgs.coreutils}/bin/mktemp)"
        ${pkgs.coreutils}/bin/printf '%s\n' \
          "path \"$mount/issue/$role\" {" \
          '  capabilities = ["create", "update"]' \
          '}' \
          "path \"$mount/cert/ca\" {" \
          '  capabilities = ["read"]' \
          '}' \
          "path \"$kv_mount/data/nodes/$node_fqdn\" {" \
          '  capabilities = ["read"]' \
          '}' \
          "path \"$kv_mount/data/$recipient_public_key_kv_path\" {" \
          '  capabilities = ["read"]' \
          '}' > "$policy_file"
        vault policy write "$policy" "$policy_file" >/dev/null
        ${pkgs.coreutils}/bin/rm -f "$policy_file"
        policy_file=""

        vault write "auth/approle/role/$role" \
          token_policies="$policy" \
          token_ttl=1h \
          token_max_ttl=4h \
          secret_id_ttl=0 \
          secret_id_num_uses=0 >/dev/null

        ${pkgs.jq}/bin/jq -n \
          --arg node_fqdn "$node_fqdn" \
          --arg role "$role" \
          --arg policy "$policy" \
          '{event:"vault.hub_site_reconciled", node_fqdn:$node_fqdn, role:$role, policy:$policy}'
      }

      for node_fqdn in "$@"; do
        reconcile_site "$node_fqdn"
      done

      trap - EXIT
      cleanup
    '';
  };

  hubSiteEnrollmentTool = pkgs.writeShellApplication {
    name = "luxnix-vault-enroll-hub-site";
    runtimeInputs = [
      hubSitesReconcileTool
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.jq
      pkgs.openssl
      pkgs.vault
    ];
    text = ''
      set -euo pipefail
      umask 077

      if [ "$#" -ne 2 ]; then
        echo "Usage: luxnix-vault-enroll-hub-site <site-node-fqdn> <output-directory>" >&2
        exit 2
      fi
      if [ -z "''${VAULT_ADDR:-}" ] || [ -z "''${VAULT_TOKEN:-}" ]; then
        echo "VAULT_ADDR and a short-lived administrative VAULT_TOKEN are required." >&2
        exit 1
      fi

      node_fqdn="$1"
      output_directory="$2"
      case "$node_fqdn" in
        *[!A-Za-z0-9.-]*|.*|*..*|*.)
          echo "site-node-fqdn must be a valid DNS name" >&2
          exit 2
          ;;
      esac
      role="site-$(${pkgs.coreutils}/bin/printf '%s' "$node_fqdn" | ${pkgs.coreutils}/bin/tr '.-' '__')"
      mount=${lib.escapeShellArg hubPkiCfg.mountPath}
      kv_mount=${lib.escapeShellArg hubPkiCfg.kvMountPath}

      if ! vault status >/dev/null; then
        echo "Vault must be initialized and unsealed before site enrollment." >&2
        exit 1
      fi

      # Reconcile policy, PKI role, and AppRole without issuing credentials.
      # Credential issuance remains explicit and happens only below.
      luxnix-vault-reconcile-hub-sites "$node_fqdn" >/dev/null

      ${pkgs.coreutils}/bin/install -d -m 0700 "$output_directory"
      role_id_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.role-id.XXXXXX")"
      secret_id_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.secret-id.XXXXXX")"
      ca_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.client-ca.XXXXXX")"
      server_ca_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.server-ca.XXXXXX")"
      server_ca_fingerprint_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.server-ca-fingerprint.XXXXXX")"
      node_secret_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.node-secret.XXXXXX")"
      node_secret_error="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.node-secret-error.XXXXXX")"
      cleanup_outputs() {
        ${pkgs.coreutils}/bin/rm -f \
          "$role_id_tmp" \
          "$secret_id_tmp" \
          "$ca_tmp" \
          "$server_ca_tmp" \
          "$server_ca_fingerprint_tmp" \
          "$node_secret_tmp" \
          "$node_secret_error"
      }
      trap cleanup_outputs EXIT

      vault read -field=role_id "auth/approle/role/$role/role-id" > "$role_id_tmp"
      vault write -field=secret_id -f "auth/approle/role/$role/secret-id" > "$secret_id_tmp"
      vault read -field=certificate "$mount/cert/ca" > "$ca_tmp"
      ${pkgs.coreutils}/bin/cp ${lib.escapeShellArg (toString serverCfg.caCertFile)} "$server_ca_tmp"
      server_ca_fingerprint="$(${pkgs.openssl}/bin/openssl x509 \
        -in "$server_ca_tmp" -noout -fingerprint -sha256 \
        | ${pkgs.coreutils}/bin/cut -d= -f2)"
      ${pkgs.coreutils}/bin/printf '%s\n' "$server_ca_fingerprint" > "$server_ca_fingerprint_tmp"

      if ! vault kv get -field=shared_secret "$kv_mount/nodes/$node_fqdn" \
        > "$node_secret_tmp" 2> "$node_secret_error"; then
        if ! ${pkgs.gnugrep}/bin/grep -Fq 'No value found at' "$node_secret_error"; then
          echo "ERROR: failed to read the site node secret; refusing to treat the Vault error as an absent secret." >&2
          exit 1
        fi

        ${pkgs.openssl}/bin/openssl rand -base64 48 \
          | ${pkgs.coreutils}/bin/tr -d '\n' > "$node_secret_tmp"
        if ! vault kv put -cas=0 "$kv_mount/nodes/$node_fqdn" shared_secret=- \
          < "$node_secret_tmp" >/dev/null; then
          # A concurrent enrollment may have created the record first. Re-read
          # it; any other failure remains fatal.
          vault kv get -field=shared_secret "$kv_mount/nodes/$node_fqdn" \
            > "$node_secret_tmp"
        fi
      fi
      if [ ! -s "$node_secret_tmp" ]; then
        echo "ERROR: Vault returned an empty site node secret." >&2
        exit 1
      fi

      ${pkgs.coreutils}/bin/chmod 0400 "$role_id_tmp" "$secret_id_tmp" "$ca_tmp" \
        "$server_ca_tmp" "$server_ca_fingerprint_tmp" "$node_secret_tmp"
      ${pkgs.coreutils}/bin/mv -f "$role_id_tmp" "$output_directory/approle_role_id"
      ${pkgs.coreutils}/bin/mv -f "$secret_id_tmp" "$output_directory/approle_secret_id"
      ${pkgs.coreutils}/bin/mv -f "$ca_tmp" "$output_directory/client-ca.pem"
      ${pkgs.coreutils}/bin/mv -f "$server_ca_tmp" "$output_directory/vault-server-ca.pem"
      ${pkgs.coreutils}/bin/mv -f "$server_ca_fingerprint_tmp" "$output_directory/vault-server-ca.sha256"
      ${pkgs.coreutils}/bin/mv -f "$node_secret_tmp" "$output_directory/source-node-secret"
      ${pkgs.coreutils}/bin/rm -f "$node_secret_error"
      trap - EXIT

      echo "Enrollment material created in $output_directory. Transfer it through an approved secret-delivery channel."
      echo "Vault server CA SHA-256: $server_ca_fingerprint"
      echo "Configured client PKI/AppRole identity: $role."
    '';
  };

  managedServerTlsTool = pkgs.writeShellApplication {
    name = "luxnix-vault-maintain-server-tls";
    runtimeInputs = [
      pkgs.bash
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.openssl
    ];
    text = builtins.readFile ../../../../scripts/vault/maintain-server-tls.sh;
  };

  vaultAuthErrorClassifierTool = pkgs.writeShellApplication {
    name = "luxnix-vault-classify-auth-error";
    runtimeInputs = [ pkgs.gnugrep ];
    text = builtins.readFile ../../../../scripts/vault/classify-auth-error.sh;
  };

  managedServerTlsCommand = lib.escapeShellArgs (
    [
      "${managedServerTlsTool}/bin/luxnix-vault-maintain-server-tls"
      "--state-dir"
      managedTlsCfg.stateDirectory
      "--ca-cert"
      (toString serverCfg.caCertFile)
      "--ca-key"
      managedTlsCfg.caKeyFile
      "--server-cert"
      (toString serverCfg.tlsCertFile)
      "--server-key"
      (toString serverCfg.tlsKeyFile)
      "--read-group"
      config.luxnix.generic-settings.sensitiveServiceGroupName
      "--ca-common-name"
      managedTlsCfg.caCommonName
      "--server-common-name"
      managedTlsCfg.serverCommonName
      "--ca-validity-days"
      (toString managedTlsCfg.caValidityDays)
      "--leaf-validity-days"
      (toString managedTlsCfg.leafValidityDays)
      "--renew-before-days"
      (toString managedTlsCfg.renewBeforeDays)
      "--rotation-marker"
      "${runtimeDir}/server-leaf-rotated"
    ]
    ++ lib.concatMap (name: [
      "--dns-name"
      name
    ]) managedTlsCfg.dnsNames
    ++ lib.concatMap (address: [
      "--ip-address"
      address
    ]) managedTlsCfg.ipAddresses
  );
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

  issueHubClientCertificateScript = pkgs.writeShellScript "issue-lx-hub-client-certificate" ''
    set -euo pipefail
    umask 077

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

    if [ -s "$certificate" ] && [ -s "$private_key" ] \
      && ${pkgs.openssl}/bin/openssl x509 -in "$certificate" -noout \
        -checkend ${toString clientHubPkiCfg.renewBeforeSeconds} \
      && certificate_matches_key; then
      exit 0
    fi

    if [ ! -s ${lib.escapeShellArg runtimeEnvironmentFile} ]; then
      state="enrollment-pending"
      if [ -s ${lib.escapeShellArg runtimeStatusFile} ]; then
        state="$(${pkgs.coreutils}/bin/cat ${lib.escapeShellArg runtimeStatusFile})"
      fi
      ${optionalString cfg.client.allowOffline ''
        if [ -s "$certificate" ] && [ -s "$private_key" ] && [ -s "$client_ca" ]; then
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
        if [ -s "$certificate" ] && [ -s "$private_key" ] && [ -s "$client_ca" ]; then
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
    trap - EXIT
  '';

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
  vaultAuthSetupScript = pkgs.writeShellScript "luxnix-vault-auth-setup" ''
    set -euo pipefail
    umask 077

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

    client = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = true;
            description = "Enable runtime Vault client bootstrap for systemd services.";
          };

          allowOffline = mkOption {
            type = types.bool;
            default = false;
            description = ''
              Allow activation to continue when Vault is temporarily unreachable.
              Services may reuse already deployed secret files, but initial
              provisioning still fails when a required local secret is absent.
            '';
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

          runtimeStatusFile = mkOption {
            type = types.str;
            default = runtimeStatusFile;
            readOnly = true;
            description = "Generated non-secret Vault client status file used for operator diagnostics.";
          };

          auth = mkOption {
            type = types.submodule {
              options = {
                method = mkOption {
                  type = types.enum [
                    "none"
                    "tokenFile"
                    "approle"
                  ];
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

                deferUntilProvisioned = mkOption {
                  type = types.bool;
                  default = false;
                  description = ''
                    Temporarily skip vault-auth-setup without failing system
                    activation while initial AppRole enrollment is incomplete.
                    This does not let lx-annotate start without its secrets.
                    Disable this option after the first successful login so
                    subsequent authentication failures remain strict.
                  '';
                };
              };
            };
            default = { };
            description = "Vault authentication bootstrap for LuxNix systemd services.";
          };
          hubPki = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Issue and renew this site's hub-transfer client identity from Vault.";
                };
                mountPath = mkOption {
                  type = types.strMatching "[A-Za-z0-9_-]+";
                  default = "lx-hub-pki";
                  description = "Vault PKI mount containing the enrolled site role.";
                };
                roleName = mkOption {
                  type = types.strMatching "[A-Za-z0-9_-]+";
                  default = "site-${
                    lib.replaceStrings [ "." "-" ] [ "_" "_" ] "${config.networking.hostName}.intern"
                  }";
                  description = "Per-site Vault PKI role created by luxnix-vault-enroll-hub-site.";
                };
                commonName = mkOption {
                  type = types.str;
                  default = "${config.networking.hostName}.intern";
                  description = "Exact DNS identity requested for the site-node client certificate.";
                };
                ttl = mkOption {
                  type = types.str;
                  default = "720h";
                  description = "Requested client-certificate lifetime.";
                };
                renewBeforeSeconds = mkOption {
                  type = types.ints.positive;
                  default = 7 * 24 * 60 * 60;
                  description = "Renew the client certificate when less than this lifetime remains.";
                };
                certificateFile = mkOption {
                  type = types.str;
                  default = "/var/lib/lx-annotate/hub-pki/client.crt";
                  description = "Atomic runtime path for the issued client certificate.";
                };
                keyFile = mkOption {
                  type = types.str;
                  default = "/var/lib/lx-annotate/hub-pki/client.key";
                  description = "Atomic runtime path for the issued client private key.";
                };
                caCertificateFile = mkOption {
                  type = types.str;
                  default = "/var/lib/lx-annotate/hub-pki/client-ca.pem";
                  description = "Atomic runtime path for the issuing client CA certificate.";
                };
                kvMountPath = mkOption {
                  type = types.strMatching "[A-Za-z0-9_-]+";
                  default = "lx-hub-secrets";
                  description = "Vault KV v2 mount containing this site's request-authentication secret.";
                };
                nodeSecretFile = mkOption {
                  type = types.str;
                  default = "/etc/secrets/vault/hub-pki/source-node-secret";
                  description = "Runtime path for the Vault-delivered NetworkNode request-authentication secret.";
                };
                recipientPublicKeyFile = mkOption {
                  type = types.str;
                  default = "/etc/secrets/vault/hub-pki/hub-recipient-current.pub.pem";
                  description = "Atomic runtime path for the Vault-delivered central-hub X25519 public recipient key.";
                };
                recipientPublicKeyKvPath = mkOption {
                  type = types.strMatching "[A-Za-z0-9_/-]+";
                  default = "hub/envelope-recipient/current";
                  description = "Vault KV v2 path containing only the central-hub X25519 public recipient key.";
                };
              };
            };
            default = { };
            description = "Vault-issued LX-Annotate outbound hub-transfer identity.";
          };
        };
      };
      default = { };
      description = "Vault client configuration used by secret-provisioning services.";
    };

    server = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = false;
            description = "Run a production HashiCorp Vault server with integrated Raft storage.";
          };
          bindAddress = mkOption {
            type = types.str;
            default = "127.0.0.1:8200";
            description = "Vault TCP listener address. Restrict non-loopback listeners with the host firewall.";
          };
          apiAddress = mkOption {
            type = types.str;
            default = "https://127.0.0.1:8200";
            description = "Canonical HTTPS API address advertised by Vault.";
          };
          clusterAddress = mkOption {
            type = types.str;
            default = "https://127.0.0.1:8201";
            description = "Canonical HTTPS Raft cluster address advertised by Vault.";
          };
          nodeId = mkOption {
            type = types.strMatching "[A-Za-z0-9._-]+";
            default = config.networking.hostName;
            description = "Stable Vault integrated-storage node identifier.";
          };
          storagePath = mkOption {
            type = types.path;
            default = "/var/lib/vault";
            description = "Vault integrated Raft storage path. Vault barrier-encrypts its contents.";
          };
          tlsCertFile = mkOption {
            type = types.nullOr types.path;
            default = null;
            description = "Runtime PEM server certificate; must not contain private material in the Nix store.";
          };
          tlsKeyFile = mkOption {
            type = types.nullOr types.path;
            default = null;
            description = "Runtime PEM server private key; must remain outside the Nix store.";
          };
          caCertFile = mkOption {
            type = types.nullOr types.path;
            default = null;
            description = "Optional CA used by local provisioning clients to verify the Vault server certificate.";
          };
          managedTls = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Create one persistent local CA and renew only the CA-signed Vault server leaf.";
                };
                stateDirectory = mkOption {
                  type = types.str;
                  default = "/var/lib/luxnix-vault-pki";
                  description = "Root-only persistent directory containing the Vault server CA and leaf material.";
                };
                caKeyFile = mkOption {
                  type = types.str;
                  default = "${serverCfg.managedTls.stateDirectory}/ca.key";
                  description = "Persistent root-only Vault server CA key; it is never automatically replaced.";
                };
                caCommonName = mkOption {
                  type = types.str;
                  default = "LuxNix Vault Server CA";
                  description = "Common name used only when initially creating the stable Vault server CA.";
                };
                serverCommonName = mkOption {
                  type = types.str;
                  default = "vault.endo-reg.net";
                  description = "Common name of renewed Vault server leaf certificates.";
                };
                dnsNames = mkOption {
                  type = types.listOf types.str;
                  default = [ ];
                  description = "DNS subject alternative names required in every Vault server leaf.";
                };
                ipAddresses = mkOption {
                  type = types.listOf types.str;
                  default = [ ];
                  description = "IP subject alternative names required in every Vault server leaf.";
                };
                caValidityDays = mkOption {
                  type = types.ints.positive;
                  default = 3650;
                  description = "Validity of the CA when it is first created; CA renewal is always manual.";
                };
                leafValidityDays = mkOption {
                  type = types.ints.positive;
                  default = 90;
                  description = "Validity of each automatically renewed Vault server leaf.";
                };
                renewBeforeDays = mkOption {
                  type = types.ints.positive;
                  default = 14;
                  description = "Renew a Vault leaf this many days before expiry; never renew the CA automatically.";
                };
              };
            };
            default = { };
            description = "Stable local CA and renewable server-leaf lifecycle for Vault TLS.";
          };
          hubPki = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Expose fail-closed tooling and CA publication for LX-Annotate hub-transfer mTLS.";
                };
                mountPath = mkOption {
                  type = types.strMatching "[A-Za-z0-9_-]+";
                  default = "lx-hub-pki";
                  description = "Vault PKI secrets-engine mount used exclusively for hub-transfer client identities.";
                };
                kvMountPath = mkOption {
                  type = types.strMatching "[A-Za-z0-9_-]+";
                  default = "lx-hub-secrets";
                  description = "Vault KV v2 mount used for per-site request-authentication secrets.";
                };
                clientRoleName = mkOption {
                  type = types.strMatching "[A-Za-z0-9_-]+";
                  default = "lx-hub-site-node";
                  description = "Vault PKI role that issues client-only site-node certificates.";
                };
                caCommonName = mkOption {
                  type = types.str;
                  default = "LuxNix LX-Annotate Hub Transfer Client CA";
                  description = "Subject common name for the internal hub-transfer client CA.";
                };
                allowedDnsSuffix = mkOption {
                  type = types.str;
                  default = "intern";
                  description = "DNS suffix allowed in issued site-node client certificate names.";
                };
                maxTtl = mkOption {
                  type = types.str;
                  default = "87600h";
                  description = "Maximum lifetime of the internal transfer CA.";
                };
                clientTtl = mkOption {
                  type = types.str;
                  default = "720h";
                  description = "Maximum lifetime of issued site-node client certificates.";
                };
                caCertificateFile = mkOption {
                  type = types.str;
                  default = "/var/lib/lx-annotate/hub-pki/client-ca.pem";
                  description = "Atomic runtime publication path consumed by the hub Nginx client-certificate verifier.";
                };
                recipientPublicKeyFile = mkOption {
                  type = types.str;
                  default = "/etc/secrets/vault/hub-pki/hub-recipient-current.pub.pem";
                  description = "Operator-provisioned central-hub X25519 public recipient key published to authenticated site nodes; the corresponding private key never enters Vault site policy.";
                };
                recipientPublicKeyKvPath = mkOption {
                  type = types.strMatching "[A-Za-z0-9_/-]+";
                  default = "hub/envelope-recipient/current";
                  description = "Vault KV v2 path containing only the current central-hub envelope recipient public key.";
                };
              };
            };
            default = { };
            description = "Vault-backed LX-Annotate hub-transfer PKI configuration.";
          };
        };
      };
      default = { };
      description = "Production Vault server and service-specific PKI configuration.";
    };
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion = !vaultAuthEnabled || cfg.client.address != null || cfg.client.environmentFile != null;
        message = "luxnix.vault.client.address or luxnix.vault.client.environmentFile must be set when Vault auth bootstrap is enabled.";
      }
      {
        assertion = cfg.client.auth.method != "tokenFile" || cfg.client.auth.tokenFile != null;
        message = "luxnix.vault.client.auth.tokenFile must be set when auth.method = \"tokenFile\".";
      }
      {
        assertion =
          cfg.client.auth.method != "approle"
          || (cfg.client.auth.roleIdFile != null && cfg.client.auth.secretIdFile != null);
        message = "luxnix.vault.client.auth.roleIdFile and secretIdFile must be set when auth.method = \"approle\".";
      }
      {
        assertion =
          !cfg.client.auth.deferUntilProvisioned
          || (
            cfg.client.auth.method == "approle"
            && cfg.client.auth.roleIdFile != null
            && cfg.client.auth.secretIdFile != null
            && cfg.client.caCertFile != null
          );
        message = "luxnix.vault.client.auth.deferUntilProvisioned requires AppRole authentication files and a Vault CA certificate file.";
      }
      {
        assertion = !serverCfg.enable || (serverCfg.tlsCertFile != null && serverCfg.tlsKeyFile != null);
        message = "luxnix.vault.server.enable requires runtime TLS certificate and key files.";
      }
      {
        assertion =
          !managedTlsCfg.enable
          || (
            serverCfg.enable
            && serverCfg.caCertFile != null
            && serverCfg.tlsCertFile != null
            && serverCfg.tlsKeyFile != null
            && serverCfg.caCertFile != serverCfg.tlsCertFile
            && managedTlsCfg.dnsNames != [ ]
          );
        message = "luxnix.vault.server.managedTls requires Vault, distinct CA/leaf paths, and at least one DNS SAN.";
      }
      {
        assertion =
          !managedTlsCfg.enable
          || lib.all (path: builtins.dirOf path == managedTlsCfg.stateDirectory) [
            (toString serverCfg.caCertFile)
            managedTlsCfg.caKeyFile
            (toString serverCfg.tlsCertFile)
            (toString serverCfg.tlsKeyFile)
          ];
        message = "Managed Vault CA and server-leaf files must share managedTls.stateDirectory.";
      }
      {
        assertion =
          !managedTlsCfg.enable
          || (
            managedTlsCfg.leafValidityDays > managedTlsCfg.renewBeforeDays
            && managedTlsCfg.caValidityDays > managedTlsCfg.renewBeforeDays
            && lib.elem managedTlsCfg.serverCommonName managedTlsCfg.dnsNames
          );
        message = "Managed Vault TLS validity must exceed its renewal window, and the server common name must be a DNS SAN.";
      }
      {
        assertion = !serverCfg.enable || lib.hasPrefix "https://" serverCfg.apiAddress;
        message = "luxnix.vault.server.apiAddress must use https://.";
      }
      {
        assertion = !hubPkiCfg.enable || serverCfg.enable;
        message = "luxnix.vault.server.hubPki.enable requires the Vault server.";
      }
      {
        assertion = !hubPkiCfg.enable || serverCfg.caCertFile != null;
        message = "luxnix.vault.server.hubPki.enable requires the stable Vault server CA file.";
      }
      {
        assertion = !clientHubPkiCfg.enable || vaultAuthEnabled;
        message = "luxnix.vault.client.hubPki.enable requires tokenFile or AppRole Vault authentication.";
      }
      {
        assertion =
          !clientHubPkiCfg.enable
          || (
            let
              certificateDir = builtins.dirOf clientHubPkiCfg.certificateFile;
            in
            builtins.dirOf clientHubPkiCfg.keyFile == certificateDir
            && builtins.dirOf clientHubPkiCfg.caCertificateFile == certificateDir
          );
        message = "Vault hub client certificate, key, and CA files must share one protected runtime directory.";
      }
    ];

    services.vault = lib.mkIf serverCfg.enable {
      enable = true;
      address = serverCfg.bindAddress;
      tlsCertFile = toString serverCfg.tlsCertFile;
      tlsKeyFile = toString serverCfg.tlsKeyFile;
      storageBackend = "raft";
      inherit (serverCfg) storagePath;
      storageConfig = ''
        node_id = ${builtins.toJSON serverCfg.nodeId}
      '';
      extraConfig = ''
        api_addr = ${builtins.toJSON serverCfg.apiAddress}
        cluster_addr = ${builtins.toJSON serverCfg.clusterAddress}
        ui = false
        disable_mlock = false
      '';
    };

    users.users = lib.optionalAttrs serverCfg.enable {
      vault.extraGroups = [
        config.luxnix.generic-settings.sensitiveServiceGroupName
      ]
      ++ lib.optional config.services.nginx.enable "nginx";
    };

    roles.managed-secrets.customSecrets.lx_hub_source_node_secret =
      lib.mkIf (clientHubPkiCfg.enable && !cfg.client.auth.deferUntilProvisioned)
        {
          path = clientHubPkiCfg.nodeSecretFile;
          owner = "root";
          group = config.luxnix.generic-settings.sensitiveServiceGroupName;
          permissions = "640";
          description = "Vault-backed LX-Annotate NetworkNode request-authentication secret";
          customScript = true;
          refreshOnBoot = true;
          generator = ''
            ${pkgs.vault}/bin/vault kv get -field=shared_secret \
              ${lib.escapeShellArg "${clientHubPkiCfg.kvMountPath}/nodes/${clientHubPkiCfg.commonName}"} \
              | ${pkgs.coreutils}/bin/tr -d '\n' > "$TARGET_FILE"
            if [ ! -s "$TARGET_FILE" ]; then
              echo "ERROR: Vault returned an empty hub source-node secret." >&2
              exit 1
            fi
          '';
        };

    roles.managed-secrets.customSecrets.lx_hub_recipient_public_key =
      lib.mkIf (clientHubPkiCfg.enable && !cfg.client.auth.deferUntilProvisioned)
        {
          path = clientHubPkiCfg.recipientPublicKeyFile;
          owner = "root";
          group = config.luxnix.generic-settings.sensitiveServiceGroupName;
          permissions = "640";
          description = "Vault-authenticated central-hub X25519 envelope recipient public key";
          customScript = true;
          refreshOnBoot = true;
          generator = ''
            ${pkgs.vault}/bin/vault kv get -field=public_key \
              ${lib.escapeShellArg "${clientHubPkiCfg.kvMountPath}/${clientHubPkiCfg.recipientPublicKeyKvPath}"} \
              > "$TARGET_FILE"
            if [ ! -s "$TARGET_FILE" ] \
              || ! ${pkgs.openssl}/bin/openssl pkey -pubin -in "$TARGET_FILE" -text_pub -noout 2>/dev/null \
                | ${pkgs.gnugrep}/bin/grep -q X25519; then
              echo "ERROR: Vault returned an invalid central-hub X25519 recipient public key." >&2
              exit 1
            fi
          '';
        };

    environment.systemPackages =
      lib.optionals hubPkiCfg.enable [
        hubPkiBootstrapTool
        hubSitesReconcileTool
        hubSiteEnrollmentTool
        pkgs.vault
      ]
      ++ lib.optionals (cfg.client.enable && cfg.client.caCertFile != null) [
        vaultCaInstallTool
      ]
      ++ lib.optionals vaultAuthEnabled [
        vaultEnrollmentStatusTool
      ];

    systemd = {
      services = {
        vault = lib.mkIf serverCfg.enable {
          after = [
            "managed-secrets-setup.service"
          ]
          ++ lib.optional (
            config.services.luxnix.lxSsl.enable && !managedTlsCfg.enable
          ) "generate-lx-ssl.service";
          wants = [ "managed-secrets-setup.service" ];
          requires = lib.optional (
            config.services.luxnix.lxSsl.enable && !managedTlsCfg.enable
          ) "generate-lx-ssl.service";
        };

        luxnix-vault-managed-server-tls = lib.mkIf managedTlsCfg.enable {
          description = "Maintain the CA-signed Vault server leaf without rotating its CA";
          before = [ "vault.service" ] ++ lib.optional config.services.nginx.enable "nginx.service";
          requiredBy = [ "vault.service" ] ++ lib.optional config.services.nginx.enable "nginx.service";
          after = [ "systemd-tmpfiles-setup.service" ];
          requires = [ "systemd-tmpfiles-setup.service" ];
          serviceConfig = {
            Type = "oneshot";
            ExecStart = managedServerTlsCommand;
            ExecStartPost = pkgs.writeShellScript "reload-vault-after-leaf-rotation" ''
              marker=${lib.escapeShellArg "${runtimeDir}/server-leaf-rotated"}
              if [ -e "$marker" ] && ${pkgs.systemd}/bin/systemctl is-active --quiet vault.service; then
                # Vault reloads listener certificate/key file contents on SIGHUP.
                ${pkgs.systemd}/bin/systemctl kill --kill-whom=main --signal=HUP vault.service
              fi
              if [ -e "$marker" ] && ${pkgs.systemd}/bin/systemctl is-active --quiet nginx.service; then
                ${pkgs.systemd}/bin/systemctl reload nginx.service
              fi
            '';
            UMask = "0077";
          };
        };

      };

      timers.luxnix-vault-managed-server-tls = lib.mkIf managedTlsCfg.enable {
        description = "Check whether the Vault server leaf needs renewal";
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "5m";
          OnUnitActiveSec = "12h";
          RandomizedDelaySec = "30m";
          Persistent = true;
          Unit = "luxnix-vault-managed-server-tls.service";
        };
      };

      services.luxnix-vault-issue-hub-client-certificate = lib.mkIf clientHubPkiCfg.enable {
        description = "Issue or renew the LX-Annotate hub-transfer client certificate";
        wantedBy = lib.optionals (!cfg.client.auth.deferUntilProvisioned) [ "multi-user.target" ];
        before = [ "lx-annotate-celery-hub-transfer-worker.service" ];
        after = [
          "vault-auth-setup.service"
          "network-online.target"
        ];
        requires = [ "vault-auth-setup.service" ];
        wants = [ "network-online.target" ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = issueHubClientCertificateScript;
          Environment = lib.optionals cfg.client.allowOffline [
            "VAULT_CLIENT_TIMEOUT=5s"
          ];
          EnvironmentFile = "-${cfg.client.runtimeEnvironmentFile}";
          UMask = "0077";
        };
      };

      timers.luxnix-vault-issue-hub-client-certificate = lib.mkIf clientHubPkiCfg.enable {
        description = "Renew the LX-Annotate hub-transfer client certificate";
        wantedBy = lib.optionals (!cfg.client.auth.deferUntilProvisioned) [ "timers.target" ];
        timerConfig = {
          OnBootSec = "2m";
          OnUnitActiveSec = "12h";
          RandomizedDelaySec = "15m";
          Persistent = true;
          Unit = "luxnix-vault-issue-hub-client-certificate.service";
        };
      };

      services.luxnix-vault-publish-hub-client-ca = lib.mkIf hubPkiCfg.enable {
        description = "Atomically publish the Vault hub-transfer client CA";
        wantedBy = [ "multi-user.target" ];
        before = [ "nginx.service" ];
        after = [
          "vault.service"
          "network-online.target"
        ];
        requires = [ "vault.service" ];
        wants = [ "network-online.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          TimeoutStartSec = "4min";
          ExecStart = publishHubClientCaScript;
          Restart = "on-failure";
          RestartSec = "5s";
          UMask = "0027";
        };
      };

      tmpfiles.rules = [
        "d ${runtimeDir} 0700 root root - -"
        "z ${runtimeDir} 0700 root root - -"
      ];

      services.vault-auth-setup = mkIf vaultAuthEnabled {
        description = "Bootstrap Vault client environment for LuxNix system services";
        wantedBy = [ "multi-user.target" ];
        after = [
          "local-fs.target"
          "systemd-tmpfiles-setup.service"
          "network-online.target"
        ];
        requires = [ "systemd-tmpfiles-setup.service" ];
        wants = [
          "local-fs.target"
          "network-online.target"
        ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          User = "root";
          Group = "root";
          UMask = "0077";
          ExecCondition = lib.optionals cfg.client.auth.deferUntilProvisioned [
            vaultAuthProvisioningConditionScript
          ];
          ExecStart =
            if cfg.client.auth.deferUntilProvisioned then
              "${pkgs.coreutils}/bin/true"
            else
              vaultAuthSetupScript;
          ExecStop = vaultAuthCleanupScript;
          Environment = lib.optionals cfg.client.allowOffline [
            "VAULT_CLIENT_TIMEOUT=5s"
          ];
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
  };
}
