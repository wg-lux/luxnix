# Value of options.luxnix.vault; defaults derive from the shared context.
{
  lib,
  config,
  ctx,
  ...
}:
with lib;
with lib.luxnix;
let
  inherit (ctx)
    adminName
    runtimeEnvironmentFile
    runtimeTokenFile
    runtimeStatusFile
    serverCfg
    ;
in
{
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
              oidcClientSecretKvPath = mkOption {
                type = types.strMatching "[A-Za-z0-9_/-]+";
                default = "oidc/endoregdb-api";
                description = "Vault KV v2 path of the shared Keycloak client secret (field client_secret).";
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
              encryptedStorage = mkEnableOption "Mount a manually unlocked luxnix-vault-pki LUKS mapping before accessing server TLS material";
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
              sharedIdentityCenters = mkOption {
                type = types.listOf (types.strMatching "[A-Za-z0-9_-]+");
                default = [ ];
                description = ''
                  Center keys whose site nodes share one pseudonymization salt published once
                  (compare-and-set) at <kvMountPath>/centers/<key>/identity. Site policies are
                  granted read access to their own center path only. Empty by default; listing
                  a center never replaces an existing secret and never affects other centers.
                '';
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
              oidcClientSecretKvPath = mkOption {
                type = types.strMatching "[A-Za-z0-9_/-]+";
                default = "oidc/endoregdb-api";
                description = ''
                  Vault KV v2 path of the shared Keycloak client secret. Every reconciled site
                  policy may read it; only the custodian publishes it with
                  luxnix-vault-publish-oidc-client-secret, never the reconciler.
                '';
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
}
