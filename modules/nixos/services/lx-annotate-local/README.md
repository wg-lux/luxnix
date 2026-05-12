# `services.luxnix.lxAnnotateLocal`

This module manages the local `lx-annotate` deployment on LuxNix hosts.

## Structure

- [`default.nix`](/home/admin/luxnix/modules/nixos/services/lx-annotate-local/default.nix): thin wrapper that assembles the runtime context, script exports, and split submodules.
- [`runtime-context.nix`](/home/admin/luxnix/modules/nixos/services/lx-annotate-local/runtime-context.nix): canonical derived runtime paths, environment values, defaults, and helper functions shared by the module.
- [`options.nix`](/home/admin/luxnix/modules/nixos/services/lx-annotate-local/options.nix): public option surface.
- [`config.nix`](/home/admin/luxnix/modules/nixos/services/lx-annotate-local/config.nix): systemd, nginx, tmpfiles, assertions, and secret wiring.
- [`scripts.nix`](/home/admin/luxnix/modules/nixos/services/lx-annotate-local/scripts.nix): shell-script derivations used by the service units.

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

## Streamable Video Migration

The module exposes an opt-in manual migration unit for backfilling existing
videos into the streamable protected subtree:

- set `services.luxnix.lxAnnotateLocal.streamableMigration.enable = true`
- rebuild
- run `systemctl start lx-annotate-video-streamable-migration`

The module also exposes a dedicated manual post-deploy acceptance unit:

- `systemctl start lx-annotate-acceptance`

`lx-annotate-video-streamable-migration.service` runs the lx-annotate media
migration wrapper with streamable artifact synchronization enabled and the same
production environment as the main application service. It is intentionally not
enabled by default, timer-driven, or wanted by a boot target so operators can
control rollout pace and observe I/O.

`lx-annotate-acceptance.service` runs the deployed Django system checks with the
real LuxNix environment, verifies encrypted storage round-trips without
plaintext on disk, and fetches the Vite manifest through the local Nginx TLS
vhost.

## Wheel Runtime Roles

Wheel mode separates bootstrap jobs from the long-running web process:

- `lx-annotate-migrate.service` runs `runtime.commands.migrate`
- `lx-annotate-load-base-data.service` runs `runtime.commands.loadBaseData`
- `lx-annotate-boot.service` installs/prepares the wheel runtime and starts only
  `runtime.commands.web`
- `lx-annotate-celery-worker.service` runs `runtime.commands.celeryWorker`
- `lx-annotate-celery-pipeline-worker.service` runs the upload/anonymization
  queue
- `lx-annotate-celery-frame-extraction-worker.service` runs only the
  `frame_extraction` queue
- `lx-annotate-filewatcher.service` runs `runtime.commands.fileWatcherOnce` when
  set, otherwise `runtime.commands.fileWatcher`
- `lx-annotate-filewatcher.path` starts the watcher service when files are
  dropped into the runtime video, report, or preanonymized intake directories

The intake directory contract is centralized under `runtime.intakeDirs`. Defaults
mirror lx-annotate `secretspec.toml` names such as `data/import/video_import`
and `data/import/report_import`; Nix resolves `data/...` against
`runtime.encryptedDataDir`.

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

- [`kubernetes/lx-annotate`](/home/admin/luxnix/kubernetes/lx-annotate)

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
- `ENDOREG_ENABLE_HUB_TRANSFERS`
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

In other words:

- TLS and mTLS protect the channel and node identity
- `NetworkNode.shared_secret` still authenticates the request
- payload encryption beyond TLS is a later phase, not part of this module yet

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

The effective service order is:

```text
vault-auth-setup.service
  -> managed-secrets-setup.service
    -> lx-annotate-encrypted-data.service
      -> lx-annotate-boot.service
      -> lx-annotate-filewatcher.service
      -> lx-annotate-filewatcher.path
      -> lx-annotate-export-frames.service
```

That is the intended fail-closed behavior. If Vault lookup or LUKS unlock fails, the app services do not start.

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
    commands = {
      web = "$LX_ANNOTATE_WHEEL_VENV/bin/daphne -b \"$DJANGO_HOST\" -p \"$DJANGO_PORT\" lx_annotate.asgi:application";
      migrate = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django migrate --noinput --settings=lx_annotate.settings.settings_prod";
      loadBaseData = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django load_base_db_data --settings=lx_annotate.settings.settings_prod";
      fileWatcher = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django run_filewatcher --settings=lx_annotate.settings.settings_prod";
      exportFrames = "export-frames";
      celeryWorker = "$LX_ANNOTATE_WHEEL_VENV/bin/celery -A lx_annotate.celery:app worker --loglevel=INFO";
    };
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

- In wheel mode, `runtime.commands.fileWatcher`, `runtime.commands.exportFrames`,
  `runtime.commands.celeryWorker`, `runtime.commands.migrate`,
  `runtime.commands.loadBaseData`, and `runtime.commands.web` are
  wheel-entrypoint commands, not
  repo-local `manage.py` invocations.
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
