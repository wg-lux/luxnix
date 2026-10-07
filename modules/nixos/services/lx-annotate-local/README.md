# `services.luxnix.lxAnnotateLocal`

This module manages the local `lx-annotate` deployment on LuxNix hosts.

## Automatic media cleanup

`runtime.automaticMediaCleanup` defaults to `true` for every enabled host. The
shared environment renders `UPLOAD_JOB_SOURCE_REAPER_APPLY_ENABLED=true` for the
existing 15-minute maintenance task. Set the typed option to `false` for dry-run
operation; do not override its environment variable through `extraEnvironment`.
The backend validates ownership, current source integrity, available streaming
replacement and media leases before removing obsolete derivatives and their
terminal records. Unknown files and uncertain master replacements remain blocked.
Deploy the matching Endoreg cleanup implementation with this configuration and
inspect `periodic_hls_cleanup` / `periodic_generation_cleanup` events after
activation. The option does not perform deployment or run manual filesystem
deletion. Readiness evidence belongs to
[`lx_annotate_hls_operational_readiness.yml`](../../../../feature-tracking/lx_annotate_hls_operational_readiness.yml).

## Structure

- [`default.nix`](default.nix): thin wrapper that assembles the runtime context, script exports, and split submodules.
- [`runtime-context.nix`](runtime-context.nix): canonical derived runtime paths, environment values, defaults, and helper functions shared by the module.
- [`options.nix`](options.nix): compatibility aggregator for the public option surface.
- [`options/`](options/): one readable module per top-level configuration group; public option paths remain under `services.luxnix.lxAnnotateLocal`.
- [`config.nix`](config.nix): centralized shared configuration, assertions, secret wiring, and the explicit context passed to subservices.
- [`worker.nix`](worker.nix): typed internal worker constructor; see [worker configuration shapes](Workers.md) for fields, validation, and extension rules.
- [`subservices/`](subservices/): one systemd service per leaf file. A matching timer or path unit stays beside the service it triggers; `workers.nix` is only an aggregator.
- [`scripts.nix`](scripts.nix): shell-script derivations used by the service units.
- [`scripts/env.nix`](scripts/env.nix): single source of truth for shared lx-annotate runtime environment variables.

## OCR runtime dependencies

The service provides `runtime.tesseractPackage` with German (`deu`) and English
(`eng`) traineddata, matching the language selection in lx-anonymizer/package.nix.
The default `runtime.tessdataPrefix` references that package's `share/tessdata`
directory in the Nix store. The shared environment exports `TESSDATA_PREFIX`,
and application services and wheel maintenance wrappers include the package in
`PATH`. Neither a global Tesseract installation nor a system-profile tessdata
symlink is required. Wheel builds (`make package`) do not bundle these native
dependencies; the NixOS service closure supplies them.

The Endoreg role delegates to this service default unless its
`runtime.tessdataPrefix` is explicitly set. Apply the NixOS configuration through
the normal deployment process to update running services. The corresponding
contract is tracked by `ocr_runtime_dependencies` in
[`lx_annotate_environment_lifecycle_audit.yml`](../../../../feature-tracking/lx_annotate_environment_lifecycle_audit.yml).

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

## Legacy identity salt enrollment

For a reviewed upgrade from identities hashed with `default_salt`, enable
`django.enrollLegacyDefaultSalt` in the host inventory and regenerate its Nix
configuration. gc-02 explicitly enables this migration. Other hosts must opt in
only after confirming their established salt and keyring-capable identity writers.

The managed-secrets service provisions three service-owned, mode-0600 files:

- `/etc/secrets/vault/lx_annotate_identity_active`: independent active salt.
- `/etc/secrets/vault/lx_annotate_identity_legacy_default`: retiring `default_salt`.
- `/etc/secrets/vault/lx_annotate_identity_keyring.yml`: manifest explicitly allowing
  the legacy salt as retiring material.

The common environment supplies `DJANGO_IDENTITY_SALT_KEYRING_FILE` to systemd
services and maintenance wrappers. Existing files are preserved; a missing active
salt cannot be regenerated after manifest publication. Back up these files through
the established secret backup process. Enrollment does not perform a bulk identity
rehash or rotate media encryption or Django signing keys.

Apply through the normal NixOS deployment and managed-secrets service. Do not use
`luxnix-secrets generate --secret` for diagnostics: that CLI displays secret values.
Verify service status, private file metadata and loader success without printing
the salt or environment contents. For externally provisioned material, use
`django.identitySaltKeyringFile` or `django.identitySaltFile` instead of enrollment.

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

1. `LX_RUNTIME_ROOT`, supplied from `runtime.encryptedDataDir`, is the single protected runtime root.
2. The application derives storage and media paths through
   `endoreg_db.utils.paths.get_runtime_paths()` and `EndoregPathsModel`.
3. `storage/streamable_videos/` is the dedicated Nginx-served subtree for authorized
   video handoff via `X-Accel-Redirect`.
4. Any path under the service-user home is an access path only unless the
   contract is explicitly redesigned.

## Environment Contract

Shared lx-annotate application environment variables are centralized in:

- [`scripts/env.nix`](scripts/env.nix)

The main attrset to inspect is `commonEnv`. It is the contract rendered into:

- systemd service `environment` attrsets through the owning module in `subservices/`
- `/var/lib/lx-annotate/.env.systemd`
- the compatibility copy at `runtime.encryptedDataDir/.env.systemd`
- shell wrappers through `commonShellExportText`
- file-mover transcode fallback environment

Worker-specific env that is still shared across generated service/script paths
also lives in `scripts/env.nix`, currently `celeryWorkerResourceEnv` and
`llmInferenceWorkerEnv`.

When adding or changing a shared lx-annotate/secretspec-style variable, update
`commonEnv` first. Do not add a parallel export block in `config.nix`, a
subservice, or `scripts.nix`. Small wrapper-only variables can stay in the wrapper that owns
them, for example `PATH`, wheel virtualenv paths, command arguments,
`CUDA_VISIBLE_DEVICES`.

The central path and hash APIs are binding acceptance requirements for future
changes; see the [environment lifecycle tracker](../../../../feature-tracking/lx_annotate_environment_lifecycle_audit.yml).
Do not export `DATA_DIR`, `STORAGE_DIR`, `LX_ANNOTATE_DATA_DIR`,
`LX_ANNOTATE_ENCRYPTED_DATA_DIR`, `PROTECTED_MEDIA_ROOT`, or the three
`LX_ANNOTATE_STREAMABLE_VIDEO_*ROOT` aliases. Application media paths come from
`EndoregPathsModel` (the central paths module), including in maintenance and
frame-export commands. Nix still derives matching directories for mount,
permission, and Nginx configuration; these are not independent application inputs.
Asset, static-file, training-staging, and secret-file settings with active
consumers remain explicit deployment inputs.
Unused `CONF_DIR` and `CONF_TEMPLATE_DIR` exports are also retired; secret-file
handles retain their configured absolute paths.

Media integrity operations use artifact `get_hash()` methods and the shared
`get_file_hash` implementation in endoreg-db. Do not add shell hashing of encrypted
artifact paths: these contain ciphertext, while artifact identity describes
authenticated plaintext. The environment and file-mover contract tests must pass
alongside endoreg-db's hash/path contract tests before accepting a related change.
This contract requires an application package using `LX_RUNTIME_ROOT`; an older
package that requires retired aliases must be upgraded before activation. The
wheel build validator rejects packages whose base settings do not call the
central `get_runtime_paths()` API. The checked-in 1.2.2 artifact predates that
contract and must be replaced by a compatible release before building for deployment.

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
- run `systemctl start lx-annotate-storage-migration`

The module also exposes a dedicated manual post-deploy acceptance unit:

- `systemctl start lx-annotate-acceptance`

`lx-annotate-storage-migration.service` retains its operational name and
runs the shared `migrate_media_storage --apply` command for videos and PDFs.
`LX_RUNTIME_ROOT` is the encrypted runtime directory; the application owns all
relative directories and the central filename policy. Known legacy artifacts are
reconciled into canonical storage after content verification. Competing content or
occupied canonical destinations fail explicitly. Original sources are retained;
legacy deletion and apply remain subject to the Endoreg feature-tracker gates in
`feature-tracking/VideoStorageNormalization.yml`.
The unit is manual and has no boot target or timer. Calling the deployed helper
without `--apply` produces a dry-run report.

For bounded runs with command arguments from the admin machine, use the Devenv
entry point. It invokes the same deployed helper as the systemd unit:

```console
devenv shell lx-annotate-streamable-migration <host> --video-id 34 --include-processed
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

Each leaf below `subservices/` starts with two review aids: `Purpose:` names
the unit boundary and `Command:` identifies the executable behavior. A leaf
declares exactly one `systemd.services` attribute. Same-name `.timer` and
`.path` triggers may be colocated because they exist solely to activate that
service. Integrations that only refine externally owned units live under
`subservices/integrations/` and state that ownership in their command note.

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

| Unit                                               | Type / trigger                        | Runtime role                                                                                                                                                                                                                                                                                                                    |
| -------------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `lx-annotate-runtime-env.service`                  | root oneshot, remains active          | Creates the runtime/config/data directories, copies the database password into the runtime config directory, normalizes Keycloak secret permissions, and writes `/var/lib/lx-annotate/.env.systemd` plus the compatibility copy under the data root.                                                                            |
| `lx-annotate-encrypted-data.service`               | optional root oneshot, remains active | Opens the configured LUKS device, mounts it at `runtime.encryptedDataDir`, fixes owner/mode on the mount point, and closes it again on stop. Enabled by `runtime.managedEncryptedData.enable`.                                                                                                                                  |
| `lx-annotate-data-recovery.service`                | manual oneshot, exposed by default    | Normal startup uses the canonical runtime root without invoking legacy recovery. `dataRecovery.runBeforeStartup = true` explicitly restores the startup dependency for a reviewed migration with compatible recovery commands. The current backend removed `migrate_data_dir`; do not enable this legacy path for that release. |
| `lx-annotate-preflight.service`                    | explicit diagnostic oneshot           | Runs comprehensive checks when requested directly or through live acceptance. It does not block normal web, worker, or HLS startup and does not cache a previous successful diagnostic run.                                                                                                                                     |
| `lx-annotate-migrate.service`                      | oneshot                               | Runs `lx-annotate-manage migrate --noinput` against the effective runtime package. On failure it applies the reviewed legacy-history repair and retries once; unrelated or unrepaired failures remain fatal. It is ordered before base-data loading, encrypted-storage validation, and the web service.                         |
| `lx-annotate-terminology-bootstrap.service`        | best-effort oneshot in wheel mode     | After the web service starts, independently registers the packaged `dgvs_reporting`, `mst_3_0`, and `star_upper_gi` bundles. A new registry activates `star_upper_gi`; an existing active selection is preserved. No LX-Annotate startup unit wants, requires, or waits for this attempt.                                       |
| `lx-annotate-load-base-data.service`               | oneshot                               | Runs `lx-annotate-load-base-data --reconcile-legacy` after successful migrations. Fresh imports and bounded legacy reconciliation are idempotent; failures block dependent startup. Requires a backend release supporting the flag. See [startup contract](../../../../docs/guides/lx-annotate-wheel-startup.yml).              |
| `lx-annotate-master-key-check.service`             | oneshot, remains active               | Runs `lx-annotate-manage verify_encrypted_storage` with the deployed environment. The web service and workers require this check so a wrong or missing application master key fails closed before user traffic or background processing starts.                                                                                 |
| `lx-annotate-center-admin-bootstrap.service`       | temporary oneshot                     | When `centerAdminBootstrap.username` is set, runs the audited `bootstrap_center_admin` command after migrations, base-data loading, and encrypted-storage validation. It refuses users without the exact synchronized `center_scope:admin` group. Clear the option after a successful bootstrap deployment.                     |
| `lx-annotate.service` / `lx-annotate-boot.service` | long-running web service              | Starts the ASGI/web entrypoint on `127.0.0.1:${django.port}`. It requires the runtime env, base data, master-key check, managed secrets, encrypted data, and local Redis/PostgreSQL units when those local services are in use.                                                                                                 |

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

To build and verify the `ExecStart` executable of every configured LX-Annotate
service without starting services, run from the LuxNix repository:

```bash
nix build --impure --file tests/lx-annotate/service-binaries.nix --argstr host gc-02 --no-link -L
```

Select the host being prepared. Evaluation alone only computes store paths;
the build verifies that the executable files exist and have execute permission.
Git-backed evaluation requires new modules to be registered with Git. In wheel
mode these are wrappers: the installed virtualenv and Django commands still
need runtime validation on the deployed host.

On that host, inspect the active command without running migration or cleanup:

```bash
systemctl show lx-annotate-storage-migration.service lx-annotate-data-cleanup.service -p ExecStart
```

Use `test -x` on the absolute `path=` value in that output. The storage-migration
wrapper is named `lx-annotate-migrate-video-streamable-storage` and calls
`lx-annotate-manage migrate_media_storage`; the unit supplies `--apply`.
Do not run its `ExecStart` merely to check whether the binary exists.

`lx-annotate-data-cleanup` archives matching legacy duplicates. Its archive and
legacy checkout may be absent when systemd creates the service namespace; the
script creates the archive only after verifying the external mount. Missing
runtime storage and legacy trees overlapping active storage fail closed.
Recurring media cleanup instead runs through Celery Beat every 15 minutes on
the maintenance worker; inspect both `lx-annotate-celery-beat.service` and
`lx-annotate-celery-worker.service` when investigating that cleanup path.

| Unit                                    | Type / trigger         | Runtime role                                                                                                                                                                                                                      |
| --------------------------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `lx-annotate-filewatcher.path`          | path unit              | Watches the standard video, report, and preanonymized directories derived from `runtime.intakeDirs.importRoot`.                                                                                                                   |
| `lx-annotate-filewatcher.service`       | path-triggered oneshot | Runs `lx-annotate-watch --once` after migrations/base data and the master-key check. It drains files already present in the watched intake directories instead of running a permanent watcher process.                            |
| `lx-annotate-sap-import.path`           | path unit              | Watches the derived `sap_import` directory for `*.zip` drops.                                                                                                                                                                     |
| `lx-annotate-sap-import.service`        | path-triggered oneshot | Waits for each SAP IS-H zip to become stable, converts it with `lx-annotate-import-sap`, writes preanonymized watcher payload into the preanonymized intake directory, and moves the original zip to processed or failed storage. |
| `lx-annotate-export-frames.service`     | manual oneshot         | Runs `lx-annotate-export-frames` and writes frame export output below the protected runtime storage tree. It is not started by a boot target.                                                                                     |
| `lx-annotate-storage-migration.service` | manual oneshot         | Backfills raw and processed streamable video artifacts into the protected streamable-video subtree according to lx-annotate's active storage policy. It is intentionally operator-started.                                        |
| `lx-annotate-acceptance.service`        | manual oneshot         | Runs Django critical checks, verifies encrypted storage, and fetches the Vite manifest through the local TLS Nginx vhost. Use it as a post-deploy smoke test.                                                                     |

The intake directory contract has one setting, `runtime.intakeDirs.importRoot`.
All standard drop and staging directories are derived from that root, and the
application receives only the canonical `LX_RUNTIME_ROOT` environment variable.

### Celery Worker Units

All worker services wait for base data and the master-key check. Workers in
`mode = "always"` are wanted by `multi-user.target` and restart on failure.
Timer-scheduled workers are started by their matching timer, and workers in
`mode = "manual"` are available for explicit operator starts only.

| Unit                                                 | Default mode               | Queues                | Runtime role                                                                                                                                                   |
| ---------------------------------------------------- | -------------------------- | --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `lx-annotate-celery-worker.service`                  | always                     | `maintenance,default` | General maintenance/default work, including post-validation behavior selected by `VIDEO_POST_VALIDATION_JOB_MODE=celery`.                                      |
| `lx-annotate-celery-pipeline-worker.service`         | always                     | `pipeline`            | Upload, import, anonymization, and other pipeline jobs separated from the default queue.                                                                       |
| `lx-annotate-celery-frame-extraction-worker.service` | `maintenance-window` timer | `frame_extraction`    | FFmpeg frame extraction and post-validation rebuild work. The default policy starts it from a timer at 22:00 and caps each activation with `RuntimeMaxSec=7h`. |
| `lx-annotate-celery-ffmpeg-worker.service`           | always                     | `ffmpeg_media`        | Heavy FFmpeg media processing with its own CPU, memory, IO, and OOM scoring profile.                                                                           |
| `lx-annotate-celery-inference-worker.service`        | always                     | `inference`           | Temporal inference jobs with stream-backed frame input and optional `CUDA_VISIBLE_DEVICES`.                                                                    |
| `lx-annotate-celery-training-worker.service`         | manual                     | `model_training`      | GPU model-training jobs using `runtime.modelTrainingStagingRoot`; exports `CUDA_VISIBLE_DEVICES`, defaulting to `0`.                                           |
| `lx-annotate-celery-llm-inference-worker.service`    | manual                     | `llm_inference`       | Ollama-backed report and metadata LLM inference. It requires and orders after `ollama.service`.                                                                |

Each worker calls `lx-annotate-worker` with an explicit hostname, queue list,
concurrency, `--prefetch-multiplier=1`, and optional child recycling. Pool
limits come from `runtime.workerPools.*`.

### Maintenance Timers

| Unit                                         | Type / trigger                  | Runtime role                                                                                                                                                                                                                                                                         |
| -------------------------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `lx-annotate-ffmpeg-stream-throttle.timer`   | legacy, disabled by default     | Starts `lx-annotate-ffmpeg-stream-throttle.service`, which asks Django whether user video streams are active and then applies runtime cgroup CPU/IO weights to the FFmpeg worker. Its last applied profile is stored in `/run/lx-annotate/ffmpeg-stream-throttle.state`.             |
| `lx-annotate-data-cleanup.timer`             | timer when `dataCleanup.enable` | Starts duplicate cleanup for legacy anonymized payloads, moving verified duplicates into the configured archive tree.                                                                                                                                                                |
| `lx-annotate-emergency-storage-relief.timer` | optional timer                  | Starts the emergency relief job when explicitly enabled. The service fails closed unless the external archive mount matches the configured device id or filesystem UUID, then archives only verified duplicates or validated export bundles. Manual starts are the default workflow. |
| `lx-annotate-hub-backup.timer`               | timer when `hub.backup.enable`  | Starts hub snapshots. The service rsyncs the encrypted runtime tree into timestamped snapshots, writes JSON manifests, maintains a `latest` symlink, and prunes by `hub.backup.retainCount`.                                                                                         |

### API request priority and trailing buffer

`runtime.frontendRequestThrottle.enable` defaults to `true`. The application
middleware reserves priority before processing paths under `/api/`,
`/endoreg-api/`, and `/dtypes-api/`, including non-browser clients. The reservation
covers response delivery, streaming completion, and disconnect cleanup. Static
files and media handed off to Nginx do not hold a reservation after Django closes
the response. No frontend header or individual SQL-query instrumentation is needed.

The root controller acknowledges each admission only after applying runtime limits
to `lx-annotate-background.slice`. This slice contains the FFmpeg, pipeline, frame
extraction, inference, training, and LLM inference workers, including their child
processes. Web, PostgreSQL, maintenance, and hub transfer services stay outside it.
The defaults are an **aggregate** `CPUQuota = "50%"` (half of one CPU),
`CPUWeight = 10`, and `IOWeight = 10`. Individual worker ceilings remain in force.
CPU and I/O scheduling do not directly cap already-running GPU kernels or external
Ollama services; this is not a GPU utilization limiter.

After the last reservation closes, `runtime.frontendRequestThrottle.tailSeconds`
(default `2`) must pass without activity before the aggregate quota is removed and
slice weights return to 100. A new request resets this buffer. The controller
checks locks every 100 ms, so restoration can occur slightly later, never earlier.
Independent shared file locks account for concurrent requests, survive controller
restarts, and are released by the kernel when a web process dies. The root-owned
lock file must not be replaced while web workers are running.

`LX_ANNOTATE_REQUEST_THROTTLE_DIRECTORY` is module-owned and passed through the
packaged runtime environment. The local socket accepts only a fixed admission byte
from the application user; no request content, SQL, user identity, arbitrary unit,
or command is sent. Admission has a five-second deadline. A configured but
unavailable controller produces HTTP 503 with `Retry-After: 1` before view execution.
An empty directory setting disables this integration for local development.

Deploy the application middleware and its runtime environment allowlist together
with this module. The web service checks the installed package's middleware and
setting before startup, so an older wheel fails explicitly. The legacy
`runtime.ffmpegStreamThrottle.enable` defaults to `false` in both the service and
client role; enabling both mechanisms is a configuration error. For a rollback to
an older application package, disable request throttling explicitly before
activation. No application release or activation is implied by local tests.

Acceptance evidence belongs to
[`lx_annotate_hls_operational_readiness.yml`](../../../../feature-tracking/lx_annotate_hls_operational_readiness.yml),
criterion `frontend_request_throttle`, and the application's `StorageOptimization.yml`,
criterion `frontend_request_priority`.

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

| Operator path                       | Mover behavior                                                                                         | Watcher contract                                                                    |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| `Video_Input` desktop link          | path-triggered source, copied into mover staging, then published below `runtime.intakeDirs.importRoot` | `lx-annotate-filewatcher.path` watches the derived `video_import` directory         |
| `PDF_Input` desktop link            | path-triggered source, copied into mover staging, then published below `runtime.intakeDirs.importRoot` | `lx-annotate-filewatcher.path` watches the derived `report_import` directory        |
| `preanonymized_import` desktop link | direct service-user access path, not moved by `move-my-files`                                          | `lx-annotate-filewatcher.path` watches the derived `preanonymized_import` directory |
| `sap_import` desktop link           | direct service-user access path for SAP intake                                                         | handled by SAP import services, not by the file watcher path unit                   |

The mover staging directory is `.move-my-files-staging` below the import root. It is
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
the derived `video_import` directory. The mover does not delete the source until the
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
- `database.ownership = "external"`
- `database.host` and `database.port`
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
   The LUKS key and UUID are written as `root:root` with `0400`. The application master key uses the configured EndoReg service user/group and `0600`.

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
- Removed `runtime.commands.*` and `source.*` options no longer configure launchers.
  Select the deployed artifact with `runtime.package` or `runtime.wheelPath`.
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

Before changing packages in the shared virtualenv, the installer verifies the
application wheel metadata and resolves both the application and dependency
override plans. It rejects PEP 440 version decreases for `lx-annotate`,
`endoreg-db`, and `lx-dtypes`, including local candidate versions and overrides
that would undo an intermediate upgrade. Failed or malformed resolver reports
are admission failures. Actual installs use exact protected-package constraints
from the admitted plans, so later index changes cannot select lower versions.
This does not provide an atomic virtualenv replacement: an unrelated installation
failure can still require operator recovery.

Migrations, legacy-history repair, data-recovery migrations, and runtime preflight
require `lx-annotate-manage check_migration_compatibility` from the selected
application release. Missing commands or histories from a newer/incompatible
release fail explicitly. Keep the modules and application wheel coherent.
Rolling back NixOS does not roll back this shared virtualenv or the database.
Previously built generations lack these guards and remain unsafe rollback
targets until separately reviewed. There is no automatic downgrade exemption;
rollback requires an independently provisioned compatible application/database
pair and an explicit recovery procedure.

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
