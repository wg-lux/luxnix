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
  serverCfg = cfg.server;
  hubPkiCfg = serverCfg.hubPki;
  clientHubPkiCfg = cfg.client.hubPki;

  hubPkiBootstrapTool = pkgs.writeShellApplication {
    name = "luxnix-vault-bootstrap-hub-pki";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.jq
      pkgs.openssl
      pkgs.vault
    ];
    text = ''
      set -euo pipefail

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

      if ! vault secrets list -format=json | jq -e --arg path "$mount/" 'has($path)' >/dev/null; then
        vault secrets enable -path="$mount" pki
      fi
      vault secrets tune -max-lease-ttl="$max_ttl" "$mount"

      if ! vault secrets list -format=json | jq -e --arg path "$kv_mount/" 'has($path)' >/dev/null; then
        vault secrets enable -path="$kv_mount" -version=2 kv
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

      echo "Vault hub-transfer PKI is ready at $mount with role $role."
    '';
  };

  hubSiteEnrollmentTool = pkgs.writeShellApplication {
    name = "luxnix-vault-enroll-hub-site";
    runtimeInputs = [
      pkgs.coreutils
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
      client_ttl=${lib.escapeShellArg hubPkiCfg.clientTtl}
      policy="lx-hub-$role"

      if ! vault status >/dev/null; then
        echo "Vault must be initialized and unsealed before site enrollment." >&2
        exit 1
      fi
      if ! vault secrets list -format=json | jq -e --arg path "$mount/" 'has($path)' >/dev/null; then
        echo "Run luxnix-vault-bootstrap-hub-pki before enrolling a site node." >&2
        exit 1
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
      trap '${pkgs.coreutils}/bin/rm -f "$policy_file"' EXIT
      ${pkgs.coreutils}/bin/printf '%s\n' \
        "path \"$mount/issue/$role\" {" \
        '  capabilities = ["create", "update"]' \
        '}' \
        "path \"$mount/cert/ca\" {" \
        '  capabilities = ["read"]' \
        '}' \
        "path \"$kv_mount/data/nodes/$node_fqdn\" {" \
        '  capabilities = ["read"]' \
        '}' > "$policy_file"
      vault policy write "$policy" "$policy_file" >/dev/null

      if ! vault auth list -format=json | jq -e 'has("approle/")' >/dev/null; then
        vault auth enable approle >/dev/null
      fi
      vault write "auth/approle/role/$role" \
        token_policies="$policy" \
        token_ttl=1h \
        token_max_ttl=4h \
        secret_id_ttl=0 \
        secret_id_num_uses=0 >/dev/null

      ${pkgs.coreutils}/bin/install -d -m 0700 "$output_directory"
      role_id_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.role-id.XXXXXX")"
      secret_id_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.secret-id.XXXXXX")"
      ca_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.client-ca.XXXXXX")"
      server_ca_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.server-ca.XXXXXX")"
      node_secret_tmp="$(${pkgs.coreutils}/bin/mktemp "$output_directory/.node-secret.XXXXXX")"
      cleanup_outputs() {
        ${pkgs.coreutils}/bin/rm -f "$role_id_tmp" "$secret_id_tmp" "$ca_tmp" "$server_ca_tmp" "$node_secret_tmp"
      }
      trap cleanup_outputs EXIT

      vault read -field=role_id "auth/approle/role/$role/role-id" > "$role_id_tmp"
      vault write -field=secret_id -f "auth/approle/role/$role/secret-id" > "$secret_id_tmp"
      vault read -field=certificate "$mount/cert/ca" > "$ca_tmp"
      ${pkgs.coreutils}/bin/cp ${lib.escapeShellArg (toString serverCfg.tlsCertFile)} "$server_ca_tmp"
      if ! vault kv get -field=shared_secret "$kv_mount/nodes/$node_fqdn" > "$node_secret_tmp" 2>/dev/null; then
        ${pkgs.openssl}/bin/openssl rand -base64 48 | ${pkgs.coreutils}/bin/tr -d '\n' > "$node_secret_tmp"
        vault kv put "$kv_mount/nodes/$node_fqdn" shared_secret=- < "$node_secret_tmp" >/dev/null
      fi
      ${pkgs.coreutils}/bin/chmod 0400 "$role_id_tmp" "$secret_id_tmp" "$ca_tmp" "$server_ca_tmp" "$node_secret_tmp"
      ${pkgs.coreutils}/bin/mv -f "$role_id_tmp" "$output_directory/approle_role_id"
      ${pkgs.coreutils}/bin/mv -f "$secret_id_tmp" "$output_directory/approle_secret_id"
      ${pkgs.coreutils}/bin/mv -f "$ca_tmp" "$output_directory/client-ca.pem"
      ${pkgs.coreutils}/bin/mv -f "$server_ca_tmp" "$output_directory/vault-server-ca.pem"
      ${pkgs.coreutils}/bin/mv -f "$node_secret_tmp" "$output_directory/source-node-secret"
      trap - EXIT

      echo "Enrollment material created in $output_directory. Transfer it through an approved secret-delivery channel."
      echo "Configure the client PKI role as $role."
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
        if ! ${pkgs.vault}/bin/vault write -field=token auth/approle/login \
          role_id="$ROLE_ID" \
          secret_id="$SECRET_ID" > "$TMP_TOKEN"; then
          ${optionalString cfg.client.allowOffline ''
            echo "WARNING: Vault authentication failed; continuing with locally cached secrets." >&2
            exit 0
          ''}
          echo "ERROR: Vault AppRole authentication failed." >&2
          exit 1
        fi
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
        assertion = !serverCfg.enable || (serverCfg.tlsCertFile != null && serverCfg.tlsKeyFile != null);
        message = "luxnix.vault.server.enable requires runtime TLS certificate and key files.";
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
      storagePath = serverCfg.storagePath;
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

    systemd.services.vault = lib.mkIf serverCfg.enable {
      after = [
        "managed-secrets-setup.service"
      ]
      ++ lib.optional config.services.luxnix.lxSsl.enable "generate-lx-ssl.service";
      wants = [ "managed-secrets-setup.service" ];
      requires = lib.optional config.services.luxnix.lxSsl.enable "generate-lx-ssl.service";
    };

    roles.managed-secrets.customSecrets.lx_hub_source_node_secret = lib.mkIf clientHubPkiCfg.enable {
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

    environment.systemPackages = lib.optionals hubPkiCfg.enable [
      hubPkiBootstrapTool
      hubSiteEnrollmentTool
      pkgs.vault
    ];

    systemd.services.luxnix-vault-issue-hub-client-certificate = lib.mkIf clientHubPkiCfg.enable {
      description = "Issue or renew the LX-Annotate hub-transfer client certificate";
      wantedBy = [ "multi-user.target" ];
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
        EnvironmentFile =
          lib.optionalString cfg.client.allowOffline "-" + cfg.client.runtimeEnvironmentFile;
        UMask = "0077";
      };
    };

    systemd.timers.luxnix-vault-issue-hub-client-certificate = lib.mkIf clientHubPkiCfg.enable {
      description = "Renew the LX-Annotate hub-transfer client certificate";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "2m";
        OnUnitActiveSec = "12h";
        RandomizedDelaySec = "15m";
        Persistent = true;
        Unit = "luxnix-vault-issue-hub-client-certificate.service";
      };
    };

    systemd.services.luxnix-vault-publish-hub-client-ca = lib.mkIf hubPkiCfg.enable {
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
        ExecStart = publishHubClientCaScript;
        Restart = "on-failure";
        RestartSec = "5s";
        UMask = "0027";
      };
    };

    systemd.tmpfiles.rules = [
      "d ${runtimeDir} 0700 root root - -"
      "z ${runtimeDir} 0700 root root - -"
    ];

    systemd.services.vault-auth-setup = mkIf vaultAuthEnabled {
      description = "Bootstrap Vault client environment for LuxNix system services";
      wantedBy = [ "multi-user.target" ];
      after = [
        "local-fs.target"
        "systemd-tmpfiles-setup.service"
        "network-online.target"
      ];
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
}
