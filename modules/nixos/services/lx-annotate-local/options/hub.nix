{
  config,
  lib,
  lxAnnotateRuntime,
  ...
}:
let
  inherit (lib) mkOption types;
  inherit (lxAnnotateRuntime.paths)
    runtimeDataRootPath
    hubBackupIncomingPath
    hubBackupSnapshotPath
    hubBackupManifestPath
    ;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    hub = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = config.networking.hostName == "gs-02";
            description = "Mark this host as the central lx-annotate hub node and enable central-node groundwork defaults.";
          };
          transferApi = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Enable the authenticated node-to-node hub transfer API. Disabled by default even on hub nodes.";
                };
                requireSecureTransport = mkOption {
                  type = types.bool;
                  default = true;
                  description = "Require HTTPS-equivalent secure transport for hub transfer requests.";
                };
                requireMtls = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Require proxy-verified mutual TLS for node-authenticated hub transfer requests.";
                };
                mtlsMetaKey = mkOption {
                  type = types.str;
                  default = "HTTP_X_CLIENT_CERT_VERIFIED";
                  description = "Django request META key used to verify proxy-attested mTLS client authentication.";
                };
                mtlsMetaValue = mkOption {
                  type = types.str;
                  default = "SUCCESS";
                  description = "Expected proxy-attested mTLS verification value forwarded to Django.";
                };
                clientCaFile = mkOption {
                  type = types.nullOr (types.either types.path types.str);
                  default = null;
                  description = "PEM bundle used by Nginx to verify client certificates for hub transfer requests.";
                };
                clientCrlFile = mkOption {
                  type = types.str;
                  default = "/var/lib/luxnix-hub-crl/client-crl.pem";
                  readOnly = true;
                  description = "Authenticated complete CRL bundle published for Nginx; initial publication is required before Nginx starts.";
                };
                crlUrls = mkOption {
                  type = types.listOf types.str;
                  default = [
                    "${config.luxnix.vault.server.apiAddress}/v1/${config.luxnix.vault.server.hubPki.mountPath}/crl/pem"
                  ];
                  description = "Direct HTTPS Vault CRL endpoints. Include a complete CRL for every CA in clientCaFile, including intermediate and root CAs. Redirects are refused.";
                };
                crlTlsCaFile = mkOption {
                  type = types.nullOr (types.either types.path types.str);
                  default = config.luxnix.vault.server.caCertFile;
                  description = "Independently provisioned Vault server CA authenticating CRL downloads. Never fetched from the CRL endpoint.";
                };
                crlMaxAgeSeconds = mkOption {
                  type = types.ints.positive;
                  default = 72 * 60 * 60;
                  description = "Maximum signed CRL age. Nginx also rejects expired CRLs; refresh failures immediately block new transfer requests. Align with Vault CRL expiry and rebuild settings.";
                };
                recipientPrivateKeyFiles = mkOption {
                  type = types.listOf types.str;
                  default = [ ];
                  description = "Ordered current and retiring X25519 PEM private recipient keys used only by the central hub to unwrap per-transfer data-encryption keys.";
                };
                maxUploadBytes = mkOption {
                  type = types.ints.positive;
                  default = 50 * 1024 * 1024 * 1024;
                  description = "Maximum accepted processed-media upload size in bytes.";
                };
                httpTimeoutSeconds = mkOption {
                  type = types.ints.positive;
                  default = 12 * 60 * 60;
                  description = "Nginx client-body and upstream I/O timeout for large hub transfer requests, in seconds.";
                };
              };
            };
            default = { };
            description = "Transfer API settings for lx-annotate hub deployments.";
          };
          outboundTransfer = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Enable automatic processed-media transfer from a site node to its configured central hub.";
                };
                requireMtls = mkOption {
                  type = types.bool;
                  default = true;
                  description = "Require an outbound mTLS client identity for every hub request.";
                };
                clientCertificateFile = mkOption {
                  type = types.nullOr (types.either types.path types.str);
                  default = null;
                  description = "Readable PEM client certificate presented by the site node.";
                };
                clientKeyFile = mkOption {
                  type = types.nullOr (types.either types.path types.str);
                  default = null;
                  description = "Readable PEM private key for the outbound client certificate; keep this outside the Nix store.";
                };
                caFile = mkOption {
                  type = types.nullOr (types.either types.path types.str);
                  default = null;
                  description = "Optional private CA bundle used to verify the central hub server certificate.";
                };
                sourceNodeSecretFile = mkOption {
                  type = types.nullOr (types.either types.path types.str);
                  default = null;
                  description = "Readable file containing the NetworkNode request-authentication secret; keep this outside the Nix store.";
                };
                recipientPublicKeyFile = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  description = "Runtime X25519 PEM public key used to wrap a fresh per-transfer data-encryption key for the central hub.";
                };
                recoveryInterval = mkOption {
                  type = types.str;
                  default = "5m";
                  description = "Systemd interval for dispatching bounded recovery of queued, stale, and retryable outbound transfers.";
                };
                requestTimeoutSeconds = mkOption {
                  type = types.ints.positive;
                  default = 12 * 60 * 60;
                  description = "HTTP response timeout for synchronous registration imports and encrypted media apply, in seconds.";
                };
                taskSoftTimeLimitSeconds = mkOption {
                  type = types.ints.positive;
                  default = 13 * 60 * 60;
                  description = "Celery soft time limit for one outbound hub transfer task; this must exceed requestTimeoutSeconds so the HTTP client can persist a bounded failure first.";
                };
                taskHardTimeLimitSeconds = mkOption {
                  type = types.ints.positive;
                  default = 14 * 60 * 60;
                  description = "Celery hard time limit for one outbound hub transfer task; this must exceed taskSoftTimeLimitSeconds.";
                };
                staleAfterSeconds = mkOption {
                  type = types.ints.positive;
                  default = 15 * 60 * 60;
                  description = "Age in seconds after which an unchanged outbound transfer is eligible for recovery.";
                };
                maxRetries = mkOption {
                  type = types.ints.positive;
                  default = 5;
                  description = "Maximum bounded retry count for retryable outbound transfer failures.";
                };
              };
            };
            default = { };
            description = "Fail-closed outbound hub transfer settings for site nodes.";
          };
          nodeProvisioning = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Idempotently provision the local and peer NetworkNode records required for hub transfer.";
                };
                nodes = mkOption {
                  type = types.listOf (
                    types.submodule {
                      options = {
                        nodeKey = mkOption {
                          type = types.strMatching "[A-Za-z0-9_-]+";
                          description = "Immutable NetworkNode key shared by sender and hub databases.";
                        };
                        displayName = mkOption {
                          type = types.str;
                          description = "Operator-facing NetworkNode name.";
                        };
                        role = mkOption {
                          type = types.enum [
                            "central_hub"
                            "site_node"
                            "standalone"
                          ];
                          description = "NetworkNode deployment role.";
                        };
                        baseUrl = mkOption {
                          type = types.str;
                          default = "";
                          description = "HTTPS base URL used when this node is a transfer target.";
                        };
                        centerKey = mkOption {
                          type = types.nullOr types.str;
                          default = null;
                          description = "Existing Center.center_key owning this node.";
                        };
                        sharedSecretFile = mkOption {
                          type = types.nullOr (types.either types.path types.str);
                          default = null;
                          description = "Optional runtime file whose secret is hashed into this node record; never stored in Nix.";
                        };
                      };
                    }
                  );
                  default = [ ];
                  description = "Complete NetworkNode records required by this deployment.";
                };
              };
            };
            default = { };
            description = "Model-boundary provisioning for hub-transfer node identities.";
          };
          backup = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Enable protected backup groundwork on the hub node. This provisions a landing area for inbound backups and periodic local runtime snapshots.";
                };
                incomingDir = mkOption {
                  type = types.str;
                  default = hubBackupIncomingPath;
                  description = "Protected landing directory for inbound backups staged on the hub node.";
                };
                snapshotDir = mkOption {
                  type = types.str;
                  default = hubBackupSnapshotPath;
                  description = "Protected directory where the hub node stores timestamped runtime snapshots.";
                };
                manifestDir = mkOption {
                  type = types.str;
                  default = hubBackupManifestPath;
                  description = "Protected directory for JSON manifests describing generated hub snapshots.";
                };
                sourceRuntimeDir = mkOption {
                  type = types.str;
                  default = runtimeDataRootPath;
                  description = "Runtime tree snapshotted by the hub backup service. This should remain the encrypted lx-annotate data root.";
                };
                onCalendar = mkOption {
                  type = types.str;
                  default = "hourly";
                  description = "systemd timer schedule for hub runtime snapshots.";
                };
                retainCount = mkOption {
                  type = types.int;
                  default = 48;
                  description = "How many completed snapshots the hub node keeps before pruning older ones.";
                };
                minimumFreeBytes = mkOption {
                  type = types.ints.unsigned;
                  default = 10737418240;
                  description = "Minimum free bytes that must remain on the snapshot filesystem before and after staging a coupled database/media restore point.";
                };
                exclude = mkOption {
                  type = types.listOf types.str;
                  default = [
                    ".lx-annotate-rsync-partial"
                    "temp"
                    "frames"
                    "raw_frames"
                    "hub/backup/incoming"
                    "hub/backup/snapshots"
                    "hub/backup/manifests"
                  ];
                  description = "Paths excluded from hub runtime snapshots. Defaults omit disposable frame/temp output and the backup directories themselves.";
                };
              };
            };
            default = { };
            description = "Central hub backup groundwork settings.";
          };
        };
      };
      default = { };
      description = "Central hub groundwork settings for lx-annotate.";
    };
  };
}
