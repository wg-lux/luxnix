# `services.luxnix.lxAnnotateLocal`

This module manages the local `lx-annotate` deployment on LuxNix hosts.

## Structure

- [`default.nix`](default.nix): thin wrapper that assembles the runtime context, script exports, and split submodules.
- [`runtime-context.nix`](runtime-context.nix): canonical derived runtime paths, environment values, defaults, and helper functions shared by the module.
- [`options.nix`](options.nix): public option surface.
- [`config.nix`](config.nix): systemd, nginx, tmpfiles, assertions, and secret wiring.
- [`scripts.nix`](scripts.nix): shell-script derivations used by the service units.
- [`scripts/env.nix`](scripts/env.nix): single source of truth for shared lx-annotate runtime environment variables.

## Encrypted Data Flow

The module can manage the application data directory as a LUKS-backed mount:

- `runtime.managedEncryptedData.enable = true`
- systemd unit: `lx-annotate-encrypted-data.service`
- mount target: `runtime.encryptedDataDir`

When `runtime.vaultManagedEncryptedData.enable = true`, the module also wires the existing `roles.managed-secrets` service to provision:

- `/etc/secrets/vault/lx_annotate_luks.key`
- `/etc/secrets/vault/lx_annotate_luks.uuid`
- `/etc/secrets/vault/lx_annotate_master_key`

from a hostname-scoped Vault path:

- `secret/data/nodes/<networking.hostName>/lx-annotate`

The encrypted-data unit then:

1. waits for the secret provisioning service
2. reads the key file and UUID file
3. opens the LUKS device with `cryptsetup`
4. mounts it at `runtime.encryptedDataDir`

## Runtime Path Contract

For this module there is exactly one canonical protected runtime root:

- `runtime.encryptedDataDir`

Everything else is derived from that root:

- managed storage: `runtime.encryptedDataDir/storage`
- intake/workflow tree: `runtime.encryptedDataDir/import`
- streamable video tree: `runtime.encryptedDataDir/storage/streamable_videos`
- raw streamable videos: `runtime.encryptedDataDir/storage/streamable_videos/raw`
- processed streamable videos: `runtime.encryptedDataDir/storage/streamable_videos/processed`

When changing LuxNix or lx-annotate integration code, keep these rules:

1. `LX_ANNOTATE_ENCRYPTED_DATA_DIR` is the single protected root.
2. `STORAGE_DIR` is derived as `${LX_ANNOTATE_ENCRYPTED_DATA_DIR}/storage`.
3. `storage/streamable_videos/` is the dedicated Nginx-served subtree for authorized
   video handoff via `X-Accel-Redirect`.
4. Any path under the service-user home is an access path only unless the
   contract is explicitly redesigned.

## Environment Contract

Shared lx-annotate application environment variables are centralized in:

- [`scripts/env.nix`](scripts/env.nix)

The main attrset to inspect is `commonEnv`. It is the contract rendered into:

- systemd service `environment` attrsets through `config.nix`
- `/var/lib/lx-annotate/.env.systemd`
- the compatibility copy at `runtime.encryptedDataDir/.env.systemd`
- shell wrappers through `commonShellExportText`
- file-mover transcode fallback environment

Worker-specific env that is still shared across generated service/script paths
also lives in `scripts/env.nix`, currently `celeryWorkerResourceEnv` and
`llmInferenceWorkerEnv`.

When adding or changing a shared lx-annotate/secretspec-style variable, update
`commonEnv` first. Do not add a parallel export block in `config.nix` or
`scripts.nix`. Small wrapper-only variables can stay in the wrapper that owns
them, for example `PATH`, wheel virtualenv paths, command arguments,
`CUDA_VISIBLE_DEVICES`, and export-frame compatibility `DATA_DIR`/`STORAGE_DIR`.

Host-specific env overrides that do not need a dedicated LuxNix option can be
set with:

```nix
services.luxnix.lxAnnotateLocal.runtime.extraEnvironment = {
  LOG_LEVEL = "INFO";
  SOME_SECRETSPEC_FLAG = "true";
};
```

`runtime.extraEnvironment` is merged last, so it can also override a value from
`commonEnv` when a host needs an escape hatch. Prefer a typed option for values
that affect systemd ordering, nginx config, storage paths, or security policy.

For streamable media offload, the exported variable name is
`SERVE_WITH_NGINX`. The older-looking name `SERVE_FROM_NGINX` is not exported
by this module. `NGINX_PROTECTED_MEDIA_URL` is exported alongside it.

Secret values are still read from files at runtime where the application expects
process secrets. The shared env contract exports the file/path variables such as
`DJANGO_SECRET_KEY_FILE`, `DJANGO_DB_PASSWORD_FILE`,
`DJANGO_KEYCLOAK_CLIENT_SECRET_FILE`, `LX_ANNOTATE_MASTER_KEY_FILE`, and
`OIDC_RP_CLIENT_ID`; shell helpers derive process-only secret values when
needed.

## Streamable Video Migration

The full cross-repository production contract, including encrypted HLS
materialization, authenticated browser playback, deployment, hub separation,
readiness, and incident response, is documented in
[`docs/lx-annotate-secure-hls.md`](../../../../docs/lx-annotate-secure-hls.md).

The essential operational distinction is that HLS systemd oneshots are
dispatchers. A successful exit confirms that eligible work was selected and
queued; only a terminal worker result and a `ready` artifact establish that the
video is playable.

The module exposes a manual migration unit for backfilling existing videos into
the streamable protected subtree:

- rebuild
- run `systemctl start lx-annotate-video-streamable-migration`

The module also exposes a dedicated manual post-deploy acceptance unit:

- `systemctl start lx-annotate-acceptance`

`lx-annotate-video-streamable-migration.service` runs the lx-annotate
`migrate_video_streamable_storage` command with the same production environment
as the main application service. Its no-argument default lets lx-annotate sync
raw and processed streamable video artifacts according to the active storage
policy. It is intentionally not
timer-driven or wanted by a boot target so operators can control rollout pace and
observe I/O.

For bounded runs with command arguments from the admin machine, use the Devenv
entry point. It invokes the same deployed helper as the systemd unit:

```console
devenv shell lx-annotate-streamable-migration <host> --video-id 34 --processed-only
```

`lx-annotate-acceptance.service` runs the deployed Django system checks with the
real LuxNix environment, verifies encrypted storage round-trips without
plaintext on disk, and fetches the Vite manifest through the local Nginx TLS
vhost.

## Runtime Services

The module splits runtime work into short bootstrap/check jobs, one long-running
web process, path-triggered intake jobs, queue workers, and optional maintenance
timers. The main web unit is produced by the upstream `services.lx-annotate`
module and then hardened/ordered here; the surrounding `lx-annotate-*` units are
owned directly by this module.

Most application units share the same service contract: they run as
`endoreg-service-user`, load `/var/lib/lx-annotate/.env.systemd`, use the
protected runtime data root as their working directory, get the same Django,
database, Celery, storage, and encryption environment from `scripts/env.nix`,
and run with `ProtectSystem=full`, `PrivateTmp=true`, and
`NoNewPrivileges=true`. Their write access is limited to the lx-annotate
runtime, wheel, static, config, storage, and model-training staging paths. The
root-run exceptions are the environment writer and the optional encrypted-data
mount unit.

### Core Boot Units

| Unit | Type / trigger | Runtime role |
| --- | --- | --- |
| `lx-annotate-runtime-env.service` | root oneshot, remains active | Creates the runtime/config/data directories, copies the database password into the runtime config directory, normalizes Keycloak secret permissions, and writes `/var/lib/lx-annotate/.env.systemd` plus the compatibility copy under the data root. |
| `lx-annotate-encrypted-data.service` | optional root oneshot, remains active | Opens the configured LUKS device, mounts it at `runtime.encryptedDataDir`, fixes owner/mode on the mount point, and closes it again on stop. Enabled by `runtime.managedEncryptedData.enable`. |
| `lx-annotate-data-recovery.service` | oneshot, enabled by default | Runs before migrations when `dataRecovery.enable` is true. It moves or overlays legacy data/media into the current protected data root, repairs managed payloads when possible, and records recovery state so heavy recovery is not repeated unnecessarily. |
| `lx-annotate-migrate.service` | oneshot | Runs `lx-annotate-manage migrate --noinput` against the effective runtime package. It is ordered before base-data loading, encrypted-storage validation, and the web service. |
| `lx-annotate-terminology-bootstrap.service` | best-effort oneshot in wheel mode | After the web service starts, independently registers the packaged `dgvs_reporting`, `mst_3_0`, and `star_upper_gi` bundles. A new registry activates `star_upper_gi`; an existing active selection is preserved. No LX-Annotate startup unit wants, requires, or waits for this attempt. |
| `lx-annotate-load-base-data.service` | oneshot | Runs `lx-annotate-load-base-data` after successful migrations. The script logs a failed base-data load but exits successfully so schema-correct deployments can still boot. |
| `lx-annotate-master-key-check.service` | oneshot, remains active | Runs `lx-annotate-manage verify_encrypted_storage` with the deployed environment. The web service and workers require this check so a wrong or missing application master key fails closed before user traffic or background processing starts. |
| `lx-annotate-center-admin-bootstrap.service` | temporary oneshot | When `centerAdminBootstrap.username` is set, runs the audited `bootstrap_center_admin` command after migrations, base-data loading, and encrypted-storage validation. It refuses users without the exact synchronized `center_scope:admin` group. Clear the option after a successful bootstrap deployment. |
| `lx-annotate.service` / `lx-annotate-boot.service` | long-running web service | Starts the ASGI/web entrypoint on `127.0.0.1:${django.port}`. It requires the runtime env, base data, master-key check, managed secrets, encrypted data, and local Redis/PostgreSQL units when those local services are in use. |

In wheel mode, the effective runtime package is a wrapper around
`runtime.wheelPath`. The first command that needs it creates or updates the
host-local virtualenv under the service-user home, installs the wheel and any
configured wheelhouse/override packages, exports secrets from files into the
process environment, and then execs the wheel console script. The web wrapper
also syncs packaged static assets into `/var/lib/lx-annotate/staticfiles`.
The installed `lx-dtypes` dependency supplies the default terminology data
under its `site-packages/lx_dtypes/data` directory; LuxNix registers that path
directly rather than copying a mutable checkout or duplicating the bundle.

### Intake And Manual Jobs

| Unit | Type / trigger | Runtime role |
| --- | --- | --- |
| `lx-annotate-filewatcher.path` | path unit | Watches the resolved video, report, and preanonymized intake directories from `runtime.intakeDirs`. |
| `lx-annotate-filewatcher.service` | path-triggered oneshot | Runs `lx-annotate-watch --once` after migrations/base data and the master-key check. It drains files already present in the watched intake directories instead of running a permanent watcher process. |
| `lx-annotate-sap-import.path` | path unit | Watches `runtime.intakeDirs.sap` for `*.zip` drops. |
| `lx-annotate-sap-import.service` | path-triggered oneshot | Waits for each SAP IS-H zip to become stable, converts it with `lx-annotate-import-sap`, writes preanonymized watcher payload into the preanonymized intake directory, and moves the original zip to processed or failed storage. |
| `lx-annotate-export-frames.service` | manual oneshot | Runs `lx-annotate-export-frames` and writes frame export output below the protected runtime storage tree. It is not started by a boot target. |
| `lx-annotate-video-streamable-migration.service` | manual oneshot | Backfills raw and processed streamable video artifacts into the protected streamable-video subtree according to lx-annotate's active storage policy. It is intentionally operator-started. |
| `lx-annotate-acceptance.service` | manual oneshot | Runs Django critical checks, verifies encrypted storage, and fetches the Vite manifest through the local TLS Nginx vhost. Use it as a post-deploy smoke test. |

The intake directory contract is centralized under `runtime.intakeDirs`. Defaults
mirror lx-annotate `secretspec.toml` names such as `data/import/video_import`
and `data/import/report_import`; Nix resolves `data/...` against
`runtime.encryptedDataDir`.

### Celery Worker Units

All worker services wait for base data and the master-key check. Workers in
`mode = "always"` are wanted by `multi-user.target` and restart on failure.
Timer-scheduled workers are started by their matching timer, and workers in
`mode = "manual"` are available for explicit operator starts only.

| Unit | Default mode | Queues | Runtime role |
| --- | --- | --- | --- |
| `lx-annotate-celery-worker.service` | always | `maintenance,default` | General maintenance/default work, including post-validation behavior selected by `VIDEO_POST_VALIDATION_JOB_MODE=celery`. |
| `lx-annotate-celery-pipeline-worker.service` | always | `pipeline` | Upload, import, anonymization, and other pipeline jobs separated from the default queue. |
| `lx-annotate-celery-frame-extraction-worker.service` | `maintenance-window` timer | `frame_extraction` | FFmpeg frame extraction and post-validation rebuild work. The default policy starts it from a timer at 22:00 and caps each activation with `RuntimeMaxSec=7h`. |
| `lx-annotate-celery-ffmpeg-worker.service` | always | `ffmpeg_media` | Heavy FFmpeg media processing with its own CPU, memory, IO, and OOM scoring profile. |
| `lx-annotate-celery-inference-worker.service` | always | `inference` | Temporal inference jobs with stream-backed frame input and optional `CUDA_VISIBLE_DEVICES`. |
| `lx-annotate-celery-training-worker.service` | manual | `model_training` | GPU model-training jobs using `runtime.modelTrainingStagingRoot`; exports `CUDA_VISIBLE_DEVICES`, defaulting to `0`. |
| `lx-annotate-celery-llm-inference-worker.service` | manual | `llm_inference` | Ollama-backed report and metadata LLM inference. It requires and orders after `ollama.service`. |

Each worker calls `lx-annotate-worker` with an explicit hostname, queue list,
concurrency, `--prefetch-multiplier=1`, and optional child recycling. Pool
limits come from `runtime.workerPools.*`.

### Maintenance Timers

| Unit | Type / trigger | Runtime role |
| --- | --- | --- |
| `lx-annotate-ffmpeg-stream-throttle.timer` | timer, default every two minutes | Starts `lx-annotate-ffmpeg-stream-throttle.service`, which asks Django whether user video streams are active and then applies runtime cgroup CPU/IO weights to the FFmpeg worker. Its last applied profile is stored in `/run/lx-annotate/ffmpeg-stream-throttle.state`. |
| `lx-annotate-data-cleanup.timer` | timer when `dataCleanup.enable` | Starts duplicate cleanup for legacy anonymized payloads, moving verified duplicates into the configured archive tree. |
| `lx-annotate-emergency-storage-relief.timer` | optional timer | Starts the emergency relief job when explicitly enabled. The service fails closed unless the external archive mount matches the configured device id or filesystem UUID, then archives only verified duplicates or validated export bundles. Manual starts are the default workflow. |
| `lx-annotate-hub-backup.timer` | timer when `hub.backup.enable` | Starts hub snapshots. The service rsyncs the encrypted runtime tree into timestamped snapshots, writes JSON manifests, maintains a `latest` symlink, and prunes by `hub.backup.retainCount`. |

### Supporting Runtime Services

The module enables or orders against several non-`lx-annotate-*` services:

- `nginx.service` exposes the TLS vhost, proxies application traffic to the
  local web port, serves static files, and provides internal protected-media
  handoff for authorized downloads.
- `redis-lx-annotate.service` is enabled when no external Redis URL is
  configured. It listens on `127.0.0.1:6379` and uses append-only persistence so
  queued Celery work survives ordinary service or host restarts.
- `postgresql.service` and `postgres-endoreg-setup.service` are used when no
  external PostgreSQL host is configured.
- `managed-secrets-setup.service` and `vault-auth-setup.service` are part of the
  secret delivery chain when the managed-secrets/Vault roles are enabled.

## File Mover Handoff Contract

`move-my-files` and `lx-annotate-filewatcher` are coupled through the
`runtime.intakeDirs` contract. Do not give either service a parallel hardcoded
intake path.

| Operator path | Mover behavior | Watcher contract |
| --- | --- | --- |
| `Video_Input` desktop link | path-triggered source, copied into mover staging, then published to `runtime.intakeDirs.video` | `lx-annotate-filewatcher.path` watches the resolved video dir and the service exports `WATCHER_VIDEO_DIR` |
| `PDF_Input` desktop link | path-triggered source, copied into mover staging, then published to `runtime.intakeDirs.report` | `lx-annotate-filewatcher.path` watches the resolved report dir and the service exports `WATCHER_REPORT_DIR` |
| `preanonymized_import` desktop link | direct service-user access path, not moved by `move-my-files` | `lx-annotate-filewatcher.path` watches the resolved preanonymized dir and exports `WATCHER_PREANONYMIZED_DIR` |
| `sap_import` desktop link | direct service-user access path for SAP intake | handled by SAP import services, not by the file watcher path unit |

The mover staging directory is `runtime.intakeDirs.moverStaging`. It is
intentionally not watched. `move-my-files` first copies operator input into that
staging tree, fixes ownership and permissions, then moves top-level staged
entries into the watched video/report intake directories. Source files are
deleted only after the publish step succeeds; unreadable files are moved under
the `failed_input` quarantine tree. Stable video files that `ffprobe` still
rejects after 30 minutes are also quarantined so later inputs can continue.

For video entries, `move-my-files` invokes the lx-annotate/endoreg-db
`transcode_video` management command before publishing into the watched intake
directory. That command uses the existing `ffmpeg_wrapper` encoder selection and
writes the standard watcher format (H.264, `yuv420p`, full color range) into
`runtime.intakeDirs.video`. The mover does not delete the source until the
transcode command succeeds.

The watcher service runs as the same service user and group as the mover. Wheel
and repo runtime scripts both set `LX_ANNOTATE_FILEWATCHER_ARGS` to
`--process-existing-once`, so a path-triggered activation drains files that
already exist in the watched intake directories instead of requiring a
long-running watcher process.

The web command should stay a pure ASGI server command. It must not run
migrations or `load_base_db_data`; those are explicit services on NixOS and
explicit Jobs in Kubernetes-shaped deployments.

`runtime.limits` applies to the web service. `runtime.workerLimits` applies to
the Celery worker, so worker sizing can be changed without changing web service
limits.

## Frame Extraction Maintenance Windows

FFmpeg frame extraction and post-validation rebuilds are isolated on the
`frame_extraction` Celery queue. By default,
`runtime.frameExtractionWorker.mode = "maintenance-window"` keeps queued frame
jobs in Redis during normal service hours and starts
`lx-annotate-celery-frame-extraction-worker.service` from a systemd timer at
22:00 local time. The service is capped by `runtimeMaxSec = "7h"` so the window
ends before the morning workload.

Useful controls:

```bash
systemctl status lx-annotate-celery-frame-extraction-worker.timer
systemctl list-timers | grep frame-extraction
systemctl start lx-annotate-celery-frame-extraction-worker.service
systemctl stop lx-annotate-celery-frame-extraction-worker.service
```

Set `runtime.frameExtractionWorker.mode = "always"` to restore the previous
boot-started continuous worker, or `"manual"` to disable both timer and boot
autostart. The local Redis broker uses append-only persistence so queued
frame-extraction tasks survive ordinary Redis or host restarts. Production
deployments must use an lx-annotate/endoreg_db build with Celery late-ack,
worker-lost redelivery, and frame rollback support before enabling deferred
frame extraction.

## Cluster-Oriented Mode

The current NixOS default remains single-host friendly: local Redis/Postgres are
still supported, and the protected runtime root is a host path.

For cluster-oriented validation, set:

- `runtime.clustered.enable = true`
- `runtime.externalServices.redisUrl`
- `runtime.externalServices.postgresHost`
- `runtime.externalServices.postgresPort`
- `runtime.clustered.sharedStorage = true`
- `runtime.clustered.sharedMasterKeyFile = /run/secrets/lx-annotate/master-key`
- `runtime.autoGenerateMasterKey = false`

Clustered mode fails evaluation if Redis or Postgres point at localhost, if
shared storage is not acknowledged, or if per-host managed encrypted-data /
hostname-scoped Vault state is enabled. Clustered deployments must use shared
storage plus a shared workload master key for the data they share across web and
worker replicas.

The first Kubernetes package lives at:

- [`kubernetes/lx-annotate`](../../../../kubernetes/lx-annotate)

It contains plain Kustomize-managed YAML for web, worker, Service, Ingress,
ConfigMap, Secret references, a shared PVC, and singleton CronJobs with
`concurrencyPolicy: Forbid`. Run `kubernetes/lx-annotate/bootstrap-job.yaml`
explicitly with `kubectl create -f` for each release; it uses
`metadata.generateName`, applies migrations, loads base data, and writes the
release marker that web, worker, and batch pods wait for.

## Emergency Storage Relief

The module exposes a separate opt-in relief unit for storage pressure events:

- set `services.luxnix.lxAnnotateLocal.storageRelief.enable = true`
- set either `storageRelief.expectedDeviceId` or `storageRelief.expectedFsUuid`
- rebuild
- run `systemctl start lx-annotate-emergency-storage-relief`

The unit fails closed unless the external mount is active and matches the
configured device id or filesystem UUID. It writes to
`storageRelief.stagingDir` first, moves verified files into
`storageRelief.archiveDir`, emits JSON journal events, and writes a JSON
manifest under `storageRelief.manifestDir`.

The relief helper only archives:

1. legacy processed report/video duplicates whose matching database object is in
   an anonymized processed state and whose content hash matches the managed
   payload
2. export bundles that contain `.lx-annotate-export-validated.json` with
   `validated=true` and resource references whose database states are validated

Local files are deleted only after the external archive copy has been hashed and
verified. The service is manual by default; `storageRelief.timer.enable` can be
set for a scheduled emergency workflow.

## Hub Groundwork

This module can also mark a host as the first central hub node:

- `hub.enable = true`
- `django.extraSettings.IS_CENTRAL_NODE = true` is then defaulted automatically

For the current groundwork scope, hub mode does not try to implement federation,
remote trust, or cross-site reconciliation. It only establishes the host-side
contract for a central node that can:

- keep the authoritative protected runtime under `runtime.encryptedDataDir`
- run the normal lx-annotate boot, watcher, SAP import, and export services
- expose a protected backup landing area
- create timer-driven snapshots of the encrypted runtime tree

### Hub Backup Groundwork

Enable:

- `hub.backup.enable = true`

This provisions protected directories inside the encrypted runtime root:

- `hub.backup.incomingDir`
- `hub.backup.snapshotDir`
- `hub.backup.manifestDir`

and adds:

- `lx-annotate-hub-backup.service`
- `lx-annotate-hub-backup.timer`

The backup service is intentionally narrow:

1. ensures the protected backup directories exist
2. snapshots `hub.backup.sourceRuntimeDir`
3. excludes disposable paths such as `temp`, `frames`, and `raw_frames`
4. writes a JSON manifest for each snapshot
5. updates a `latest` symlink
6. prunes old snapshots by `hub.backup.retainCount`

This is groundwork only. It is safe for a central node because backup data stays
separate from active ingest paths. It does not yet implement remote transport,
remote authentication, replication policy, or restore orchestration.

### Secure Hub Transfer

The module now has an explicit Phase 1 secure-transfer contract for the
optional node-to-node hub transfer API.

For the non-technical clinical workflow, onboarding checklist, status meanings,
and failure procedure, see the
[Clinical Hub Transfer Guide](../../../../docs/clinical-hub-transfer-guide.md).

Enable transfer intake with:

- `hub.transferApi.enable = true`

When that is enabled, LuxNix now fails closed unless all of the following are
true:

- `hub.enable = true`
- `hub.transferApi.requireSecureTransport = true`
- `hub.transferApi.requireMtls = true`
- `hub.transferApi.clientCaFile` is set
- `hub.transferApi.mtlsMetaKey` is non-empty
- `hub.transferApi.mtlsMetaValue` is non-empty

This is intentional. `endoreg_db` now treats secure hub transfer as a
hostile-network workflow, so transfer enablement is no longer allowed to imply
"best effort" transport security.

The module exports the corresponding runtime environment for Django:

- `ENDOREG_DEPLOYMENT_ROLE`
- `ENDOREG_ENABLE_INCOMING_HUB_TRANSFERS`
- `ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT`
- `ENDOREG_HUB_TRANSFER_REQUIRE_MTLS`
- `ENDOREG_HUB_TRANSFER_MTLS_META_KEY`
- `ENDOREG_HUB_TRANSFER_MTLS_META_VALUE`

`ENDOREG_DEPLOYMENT_ROLE` is the explicit bridge to the
`lx-annotate`/`endoreg_db` deployment enum:

- LuxNix server or central-node deployments export `central_hub`
- LuxNix laptop center-node deployments export `site_node`
- `standalone` is reserved for isolated, non-networked test deployments

Nginx is also configured to enforce and attest client-certificate validation
for transfer-capable hub nodes:

- `ssl_verify_client optional`
- `ssl_client_certificate <client CA bundle>`
- `proxy_set_header X-Client-Cert-Verified $ssl_client_verify`

That header is then checked by Django using the configured
`ENDOREG_HUB_TRANSFER_MTLS_META_*` contract. The header is not a substitute for
Nginx verification; it is the downstream attestation of Nginx's verification
result.

Current scope:

- this protects the transfer API at the transport layer when `hub.transferApi.enable = true`
- it does not introduce payload-level envelope encryption yet
- it does not replace the separate shared-secret request authentication used by
  `NetworkNode`

Site-node sending is configured separately with
`hub.outboundTransfer.enable = true`. LuxNix fails evaluation unless the node
uses the `site_node` deployment role and supplies all of the following:

- `hub.outboundTransfer.clientCertificateFile`
- `hub.outboundTransfer.clientKeyFile`
- `hub.outboundTransfer.sourceNodeSecretFile`
- `hub.outboundTransfer.requireMtls = true`

`hub.outboundTransfer.caFile` may additionally pin a private CA for the hub's
server certificate. When outbound transfer is enabled, eligible marked jobs are
dispatched to the maintenance worker, which presents the client certificate,
verifies the hub certificate, refuses redirects, authenticates with the
separate node secret, and uploads only processed anonymized media. The private
key and node secret paths should refer to runtime-managed files outside the Nix
store.

In other words:

- TLS and mTLS protect the channel and node identity
- `NetworkNode.shared_secret` still authenticates the request
- payload encryption beyond TLS is a later phase, not part of this module yet

### Vault-backed transfer PKI

`gs-02` is the declared central hub and runs the production HashiCorp Vault
service on the VPN address `172.16.255.22:8200`. Vault uses integrated Raft
storage and its cryptographic barrier; it is never configured in development
mode. Only TCP port 8200 is opened on `tun0`.

The canonical transfer endpoint is `https://gs-02.intern`. Both
`gs-02.intern` and `vault.endo-reg.net` resolve to `172.16.255.22` inside the
LuxNix VPN. The hub generates one pinned server certificate containing both DNS
names; enrollment distributes only its public certificate to the site node.

Vault initialization and unsealing are deliberately not zero-touch. Store the
Shamir unseal shares and initial root token offline with separate custodians.
Writing an unseal key beside the Raft data would make physical disk access
sufficient to decrypt Vault and is therefore prohibited.

After the first deployment, initialize and unseal Vault through the documented
operator ceremony, then use a short-lived administrative token to configure the
dedicated transfer PKI:

```bash
export VAULT_ADDR=https://vault.endo-reg.net:8200
export VAULT_TOKEN='<short-lived-admin-token>'
luxnix-vault-bootstrap-hub-pki
sudo systemctl restart luxnix-vault-publish-hub-client-ca.service
sudo systemctl restart nginx.service
```

The bootstrap command creates an internal, Vault-held client CA, a dedicated
PKI mount, a KV v2 mount for request-authentication secrets, and client-only
certificate roles. It is idempotent and refuses to run while Vault is sealed.

Enroll a site node into a root-only temporary directory:

```bash
luxnix-vault-enroll-hub-site gc-02.intern /run/luxnix/gc-02-enrollment
```

The enrollment directory contains an AppRole role ID, AppRole secret ID, the
public client CA, the pinned Vault server certificate, and a separate
`NetworkNode` request secret. Install the role ID, secret ID, and server
certificate under `/etc/secrets/vault/hub-pki/` on the site node. Install a copy
of the request secret as
`/etc/secrets/vault/hub-pki/gc-02-source-node-secret` on the hub for the
idempotent database provisioner. Move this material only through the approved
secret-delivery channel and remove temporary copies. Do not place it in the Nix
store or version control.

On the site node, configure the Vault client with the delivered AppRole files
and enable `luxnix.vault.client.hubPki`. The
`luxnix-vault-issue-hub-client-certificate` service then issues short-lived,
client-only certificates, validates that each certificate matches its private
key, writes the files atomically, and checks twice daily whether renewal is
needed. LX-Annotate automatically takes the resulting certificate and key paths
when the Vault client PKI is enabled.

The AppRole can issue only its exact client identity, read the transfer CA, and
read its own KV request secret. The managed-secrets service installs that
request secret locally, and `lx-annotate-hub-node-provisioning` creates or
updates the matching `NetworkNode` rows through Django's model API. The hub
hashes the secret with `NetworkNode.set_shared_secret`; plaintext is never
stored in the database.

The application-level `NetworkNode` records must still use the separately
generated request secret. The Vault certificate is transport identity and must
not replace that authentication check.

On transfer API hubs, LuxNix exempts only `/api/media/hub/transfers/` from the
browser-oriented Keycloak redirect middleware. The transfer views remain
protected by Nginx client-certificate verification and their independent
`NetworkNode` key/secret authentication; global API authentication is unchanged.

## Current Security Posture

The main review caveats have now been addressed in code:

1. Vault auth is no longer ambient.
   Use `luxnix.vault.client` to provide either a token file, AppRole files, or an explicit environment file. `vault-auth-setup.service` then prepares the runtime Vault environment for `managed-secrets-setup.service`.

2. Vault-backed lx-annotate secrets now refresh on boot.
   The lx-annotate LUKS key, UUID, and application master key are configured with `refreshOnBoot = true`.

3. Hostname pathing is enforced.
   `runtime.vaultManagedEncryptedData.enable` now asserts that `networking.hostName` is set, and the secret path stays hostname-scoped.

4. Secret file permissions remain strict by design.
   The LUKS key, UUID, and application master key are written as `root:root` with `0400`.

5. The trust boundary is split in the right place.
   Vault material unlocks the mounted data directory and provides the application master key file, but the application still consumes files from the mounted path rather than raw Vault state.

## Boot Order

The core fail-closed service order is, with optional links omitted when their
options or roles are disabled:

```text
vault-auth-setup.service
  -> managed-secrets-setup.service
    -> lx-annotate-encrypted-data.service
      -> lx-annotate-runtime-env.service
        -> lx-annotate-data-recovery.service
          -> lx-annotate-migrate.service
            -> lx-annotate-load-base-data.service
              -> lx-annotate-master-key-check.service
                -> lx-annotate.service
```

`lx-annotate-boot.service` is an alias for `lx-annotate.service`. Path units,
worker units, and timer units are activated independently by systemd, but their
services still require the same runtime environment, base-data, master-key, and
encrypted-data gates before doing application work.

That is the intended fail-closed behavior. If Vault lookup, secret delivery,
LUKS unlock, feature-registry attestation, or encrypted-storage validation
fails, the app services do not start.

## Rotation Behavior

For lx-annotate, the Vault-backed files now refresh on every `managed-secrets-setup.service` run:

- `/etc/secrets/vault/lx_annotate_luks.key`
- `/etc/secrets/vault/lx_annotate_luks.uuid`
- `/etc/secrets/vault/lx_annotate_master_key`

That means node-scoped Vault rotation no longer depends on deleting the local files first.

## Recommended Host Configuration

```nix
services.luxnix.lxAnnotateLocal = {
  enable = true;
  hub = {
    enable = true;
    backup.enable = true;
  };
  runtime = {
    mode = "wheel";
    wheelPath = /path/to/dist/lx_annotate-0.0.2-py3-none-any.whl;
    wheelhousePath = /path/to/wheelhouse;
    encryptedDataDir = "/var/lib/lx-annotate/secure_data";

    managedEncryptedData = {
      enable = true;
      mapperName = "lx-annotate-data";
      fsType = "ext4";
    };

    vaultManagedEncryptedData = {
      enable = true;
      vaultPathTemplate = "secret/data/nodes/{hostname}/lx-annotate";
      setupService = "managed-secrets-setup.service";
    };

    masterKeyFile = /etc/secrets/vault/lx_annotate_master_key;
  };
};

luxnix.vault = {
  enable = true;
  client = {
    enable = true;
    address = "https://vault.example.internal:8200";
    auth.method = "approle";
    auth.roleIdFile = /etc/secrets/vault/approle_role_id;
    auth.secretIdFile = /etc/secrets/vault/approle_secret_id;
  };
};
```

Notes:

- In wheel mode, LuxNix installs `runtime.wheelPath` into a host-local
  virtualenv and exposes the wheel console scripts as a package-shaped runtime.
  The web service consumes that package through `services.lx-annotate`; LuxNix
  helper units call the same package's console scripts directly. The required
  wheel scripts are `lx-annotate-web`, `lx-annotate-manage`,
  `lx-annotate-migrate`, `lx-annotate-load-base-data`,
  `lx-annotate-worker`, `lx-annotate-watch`,
  `lx-annotate-export-frames`, and `lx-annotate-import-sap`.
- `runtime.commands.*` is retained only for legacy helper scripts and is not
  needed for the active wheel console-script runtime.
- `runtime.encryptedDataDir` remains the canonical protected root. Paths under
  the service-user home are access paths only unless the runtime contract is
  intentionally redesigned.

## Wheel Install Behavior

Wheel mode now reuses the existing virtualenv and only reinstalls when one of these changes:

- the application wheel content
- the configured wheelhouse content
- the configured Python interpreter

If `runtime.wheelhousePath` is set, installation runs with:

```text
--no-index --find-links <wheelhouse>
```

That keeps startup offline and avoids slow dependency resolution/downloads from PyPI on the host.

Without `wheelhousePath`, the first install of a new wheel version can still be slow for large Python stacks because `pip` must resolve and fetch transitive dependencies.

## How To Apply

After setting the host options, apply the system with:

```bash
nh os switch . -- --accept-flake-config
```

The expected startup order is:

1. `vault-auth-setup.service`
2. `managed-secrets-setup.service`
3. `lx-annotate-encrypted-data.service`
4. `lx-annotate-migrate.service`
5. `lx-annotate-load-base-data.service`
6. `lx-annotate-boot.service`
7. `lx-annotate-celery-worker.service`
8. `lx-annotate-celery-pipeline-worker.service`
9. `lx-annotate-celery-frame-extraction-worker.timer`

Useful verification commands:

```bash
systemctl status vault-auth-setup.service
systemctl status managed-secrets-setup.service
systemctl status lx-annotate-encrypted-data.service
systemctl status lx-annotate-migrate.service
systemctl status lx-annotate-load-base-data.service
systemctl status lx-annotate-boot.service
systemctl status lx-annotate-celery-worker.service
systemctl status lx-annotate-celery-pipeline-worker.service
systemctl status lx-annotate-celery-frame-extraction-worker.timer
systemctl status lx-annotate-celery-frame-extraction-worker.service
systemctl status lx-annotate-emergency-storage-relief.service
systemctl status lx-annotate-hub-backup.service
systemctl status lx-annotate-hub-backup.timer
ls -l /etc/secrets/vault/lx_annotate_luks.key /etc/secrets/vault/lx_annotate_luks.uuid /etc/secrets/vault/lx_annotate_master_key
```

## Safety Tests

The repo now includes a `nixtest` suite for this module and its Vault/decrypted-data safety contract.

Run it from the LuxNix repo root:

```bash
nix run .#nixtests -- --workers 1
```

The suite covers:

- Vault bootstrap contract checks
- managed-secrets atomic refresh behavior
- lx-annotate Vault secret contract checks
- reachability checks ensuring SSH survives common boot-time failures

## Remaining Requirement

The host still needs a real Vault trust root:

- a root-readable token file
- or AppRole credentials
- or a prebuilt Vault environment file

LuxNix now consumes that explicitly; it does not create Vault credentials on its own.
