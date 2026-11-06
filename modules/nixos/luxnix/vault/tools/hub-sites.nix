# Hub site registry: reconcile, OIDC secrets, lifecycle and enrollment.
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
  # Only centers explicitly listed in hubPki.sharedIdentityCenters receive a shared salt.
  centerIdentitySites = pkgs.writeText "lx-hub-center-identities.json" (
    builtins.toJSON (
      builtins.listToAttrs (
        map
          (node: {
            name = "${node.nodeKey}.${hubPkiCfg.allowedDnsSuffix}";
            value = node.centerKey;
          })
          (
            builtins.filter (
              node:
              node.role == "site_node"
              && node.centerKey != null
              && builtins.elem node.centerKey hubPkiCfg.sharedIdentityCenters
            ) config.services.luxnix.lxAnnotateLocal.hub.nodeProvisioning.nodes
          )
      )
    )
  );

  hubSitesReconcileTool = pkgs.writeShellApplication {
    name = "luxnix-vault-reconcile-hub-sites";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.jq
      pkgs.vault
      pkgs.util-linux
    ];
    text = ''
      set -euo pipefail
      umask 077
      ulimit -c 0
      install -d -m 0700 /var/lib/luxnix-vault-site-lifecycle
      exec 9>/var/lib/luxnix-vault-site-lifecycle/lock
      flock -x 9

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
      oidc_client_secret_kv_path=${lib.escapeShellArg hubPkiCfg.oidcClientSecretKvPath}
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
        local center_key=""

        case "$node_fqdn" in
          ""|*[!a-z0-9.-]*|.*|*..*|*.)
            echo "site-node-fqdn must be a valid DNS name: $node_fqdn" >&2
            return 2
            ;;
        esac

        role="site-$(${pkgs.coreutils}/bin/printf '%s' "$node_fqdn" | ${pkgs.coreutils}/bin/tr '.-' '__')"
        policy="lx-hub-$role"
        if [ -e "/var/lib/luxnix-vault-site-lifecycle/$role" ]; then
          echo "ERROR: site is contained; reconciliation cannot restore access." >&2
          return 1
        fi

        center_key="$(${pkgs.jq}/bin/jq -r --arg node "$node_fqdn" '.[$node] // empty' ${centerIdentitySites})"
        if [ -n "$center_key" ]; then
          case "$center_key" in
            *[!A-Za-z0-9_-]*)
              echo "ERROR: configured center key is invalid for identity enrollment." >&2
              return 1
              ;;
          esac
          # Only the custodian creates center material. Site policies remain read-only.
          if ! vault kv get -field=salt "$kv_mount/centers/$center_key/identity" \
            >/dev/null 2> "$state_file"; then
            if ! ${pkgs.gnugrep}/bin/grep -Fq 'No value found at' "$state_file"; then
              echo "ERROR: center identity lookup failed; refusing replacement." >&2
              return 1
            fi
            if ! ${pkgs.openssl}/bin/openssl rand -hex 32 \
              | vault kv put -cas=0 "$kv_mount/centers/$center_key/identity" salt=- >/dev/null; then
              vault kv get -field=salt "$kv_mount/centers/$center_key/identity" >/dev/null
            fi
          fi
        fi

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
          '}' \
          "path \"$kv_mount/data/$oidc_client_secret_kv_path\" {" \
          '  capabilities = ["read"]' \
          '}' > "$policy_file"
        if [ -n "$center_key" ]; then
          ${pkgs.coreutils}/bin/printf '%s\n' \
            "path \"$kv_mount/data/centers/$center_key/identity\" {" \
            '  capabilities = ["read"]' \
            '}' >> "$policy_file"
        fi
        vault policy write "$policy" "$policy_file" >/dev/null
        ${pkgs.coreutils}/bin/rm -f "$policy_file"
        policy_file=""

        vault write "auth/approle/role/$role" \
          token_policies="$policy" \
          token_type=service \
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

  # Keycloak issues the client secret; Vault only distributes it to enrolled sites.
  oidcClientSecretPublishTool = pkgs.writeShellApplication {
    name = "luxnix-vault-publish-oidc-client-secret";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.jq
      pkgs.vault
    ];
    text = ''
      set -euo pipefail
      umask 077
      ulimit -c 0

      if [ "$#" -ne 0 ]; then
        echo "Usage: luxnix-vault-publish-oidc-client-secret < secret (or enter it at the hidden prompt)" >&2
        exit 2
      fi
      if [ -z "''${VAULT_ADDR:-}" ] || [ -z "''${VAULT_TOKEN:-}" ]; then
        echo "VAULT_ADDR and a short-lived administrative VAULT_TOKEN are required." >&2
        exit 1
      fi

      kv_path=${lib.escapeShellArg "${hubPkiCfg.kvMountPath}/${hubPkiCfg.oidcClientSecretKvPath}"}
      state_file="$(mktemp)"
      error_file="$(mktemp)"
      trap 'rm -f "$state_file" "$error_file"' EXIT

      secret=""
      if [ -t 0 ]; then
        IFS= read -r -s -p "Keycloak client secret: " secret || true
        echo >&2
      else
        IFS= read -r secret || true
      fi
      if [ -z "$secret" ] || [[ "$secret" =~ [[:space:]] ]]; then
        echo "ERROR: the client secret must be one nonempty line without whitespace." >&2
        exit 1
      fi

      if vault kv get -format=json "$kv_path" > "$state_file" 2> "$error_file"; then
        current="$(jq -er '.data.data.client_secret' "$state_file")"
        version="$(jq -er '.data.metadata.version' "$state_file")"
        if [ "$current" = "$secret" ]; then
          echo "Vault already holds this client secret at $kv_path."
          exit 0
        fi
        if [ "''${LUXNIX_VAULT_ALLOW_OIDC_CLIENT_SECRET_ROTATION:-0}" != "1" ]; then
          echo "ERROR: Vault already holds a different client secret; refusing implicit rotation." >&2
          echo "Rerun with LUXNIX_VAULT_ALLOW_OIDC_CLIENT_SECRET_ROTATION=1 after rotating it in Keycloak." >&2
          exit 1
        fi
        cas="$version"
      else
        # A permission or connection error is never treated as an absent secret.
        if ! grep -Fq 'No value found at' "$error_file"; then
          echo "ERROR: client secret lookup failed; refusing to publish." >&2
          exit 1
        fi
        cas=0
      fi

      printf '%s' "$secret" | vault kv put -cas="$cas" "$kv_path" client_secret=- >/dev/null
      echo "Published the Keycloak client secret at $kv_path (check-and-set $cas)."
    '';
  };

  hubSiteLifecycleTool = pkgs.writeShellApplication {
    name = "luxnix-vault-site-lifecycle";
    runtimeInputs = [
      pkgs.vault
      pkgs.python3
    ];
    text = ''
      export LUXNIX_VAULT_KV_MOUNT=${lib.escapeShellArg hubPkiCfg.kvMountPath}
      export LUXNIX_VAULT_PKI_MOUNT=${lib.escapeShellArg hubPkiCfg.mountPath}
      export LUXNIX_VAULT_SERVER_CA=${lib.escapeShellArg (toString serverCfg.caCertFile)}
      exec python3 ${../../../../../scripts/vault/site_lifecycle.py} "$@"
    '';
  };

  hubSiteEnrollmentTool = pkgs.writeShellApplication {
    name = "luxnix-vault-enroll-hub-site";
    runtimeInputs = [
      hubSitesReconcileTool
      pkgs.util-linux
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
        ""|*[!a-z0-9.-]*|.*|*..*|*.)
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
      exec 9>/var/lib/luxnix-vault-site-lifecycle/lock
      flock -x 9
      if [ -e "/var/lib/luxnix-vault-site-lifecycle/$role" ]; then
        echo "ERROR: site is contained; enrollment cannot restore access." >&2
        exit 1
      fi

      ${verifySecretStorage} "$output_directory"
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
in
{
  inherit
    hubSitesReconcileTool
    oidcClientSecretPublishTool
    hubSiteLifecycleTool
    hubSiteEnrollmentTool
    ;
}
