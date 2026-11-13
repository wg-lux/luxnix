# LX-Annotate wheel deployment and application ownership handoff

Make the reviewed LX-Annotate wheel the primary production artifact. Move
application behavior out of LuxNix-generated Python and shell into installed
LX-Annotate commands. Keep host provisioning and systemd integration in LuxNix.
This handoff identifies implementation sources, existing application equivalents,
remaining gaps, and the tests required before deleting an OS implementation.

## Storage boundary

LuxNix owns disk encryption, unlock credentials, mount identity and startup
ordering through `luxnix.storage.operatorUnlocked`. LX-Annotate consumes the
provided runtime directory and application key file under either boot LUKS or
an existing legacy-container layout. It neither opens devices nor selects a
storage layout. Application-level file encryption and key validation remain
application responsibilities; migration must preserve the existing key.

## Source and artifact reference points

Release dependency selection was refreshed on 2026-11-03:

- `L/` means this LuxNix repository. `A/` means the LX-Annotate application
  source checkout; source references below describe ownership, not release proof.
- LuxNix selects `lx_annotate-1.7.3-py3-none-any.whl` with SRI
  `sha256-8i+igfpZK9DvYnhuVygFNnhJYJ541/92ZkqW8oXR1uQ=`. Earlier installed-artifact
  provisioning evidence remains specific to its tested 1.7.2 digest.
- Dependency installation follows the selected wheel's `Requires-Dist` metadata,
  generated from the application's `pyproject.toml`. `runtime.wheelhousePath`
  defaults to null, restoring the installation workflow from commit `8c0c8e5a`.
  Pip resolves and downloads dependencies during runtime preparation, using the
  persistent pip cache. An explicitly supplied wheelhouse enables offline
  installation with `--no-index --find-links`. No separate YAML dependency
  catalog or source archive is required. The existing guard admits the resolver
  plan and rejects protected-package downgrades before installation.
- Per operator direction, `/home/admin/endoreg-db` is implementation context for
  the next application release (1.7.3). At inspection it declared backend 1.7.7
  and contained local changes. Its source lock is not a compatible application
  lock: its asgiref constraint is older than the selected application's minimum.
  Neither that checkout nor the operator's successful gc-10 deployment identifies
  the exact historical deployed dependency closure. No deployment was changed.
- The selected wheel contains recovery, node provisioning, storage relief,
  acceptance and static-check entrypoints. Command presence alone is insufficient
  to delete an OS implementation. Terminology uses `lx-dtypes-kb-registry bootstrap`.

Start in each repository's `structure.yml` and `AGENTS.md`. Relevant application
manifests are `A/lx_annotate/structure.yml`, `A/lx_annotate/hub/structure.yml`,
`A/lx_annotate_assets/structure.yml`, `A/nix/structure.yml`, and
`A/tests/structure.yml`. Preserve the application boundary: shared clinical
models, encrypted storage and filesystem operations belong to `endoreg_db`;
knowledge-base schemas and registry operations belong to `lx_dtypes`.
LX-Annotate should expose and compose those APIs, not copy them.

## Wheel deployment files to read first

| Concern | LuxNix sources | Application and release sources | Implementation direction |
| --- | --- | --- | --- |
| Artifact selection | [options/runtime.nix](options/runtime.nix), [runtime-context.nix](runtime-context.nix), `L/flake.nix` and `L/flake.lock` | `A/pyproject.toml`, `A/uv.lock`, `A/package.nix`, `A/flake.nix` | Keep wheel URL/digest as the production release selection. LuxNix's independent endoreg-db input was removed; do not recreate it to provide runtime version metadata. The upstream flake remains the Nix module/package provider. |
| Installation and executable surface | [config.nix](config.nix): `lx_annotate_wheel_ensure`, `wheelRuntimePackage`, `make_entrypoint`; [subservices/lx-annotate-wheel-runtime.nix](subservices/lx-annotate-wheel-runtime.nix) | `A/lx_annotate/cli.py`, `A/pyproject.toml` `[project.scripts]`; `A/deployment_example/deploy.sh` | The wrapper exposes the core commands, the four packaged operational commands above and `lx-annotate-check-static` through the same prepared runtime. Unit adoption still requires behavior parity against the selected wheel. |
| Installation safety | [scripts/wheel-downgrade-guard.py](scripts/wheel-downgrade-guard.py), [scripts/wheel-python-repair.py](scripts/wheel-python-repair.py), installer in `config.nix` | `A/lx_annotate/management/commands/check_migration_compatibility.py`, `A/lx_annotate/management/commands/repair_legacy_migration_history.py` | Preserve metadata admission, protected dependency downgrade rejection, resolver constraints, locking, failure stamps and Python ABI checks. Deployment tooling remains responsible for installing the application; application commands own database compatibility checks. |
| Build and installed-artifact evidence | [scripts/wheel-static-check.py](scripts/wheel-static-check.py); `L/release-artifacts/lx-annotate/1.2.2/manifest.yml` is historical only | `A/.github/workflows/ci-cd.yml`, `A/.github/workflows/wheel-testpypi.yml`, `A/lx_annotate_assets/__init__.py`, `A/docs/guides/asset-deployment.md` | Add installed-wheel operational-command tests beside the existing release smoke tests. Record the tested wheel digest and resolved dependency versions; source-tree tests alone are insufficient. |
| Configuration and host adaptation | [scripts/env.nix](scripts/env.nix), [runtime-context.nix](runtime-context.nix), [subservices/lx-annotate-runtime-env.nix](subservices/lx-annotate-runtime-env.nix), `L/modules/nixos/roles/endoreg-client/lx-annotate.nix` | `A/secretspec.toml`, `A/lx_annotate/settings/config.py`, `A/lx_annotate/settings/settings_base.py`, `A/nix/runtime-environment.nix` | Application settings own parsing and defaults. Pass host policy, roots and secret-file handles once; retain the shared environment used by units and maintenance commands until replacement parity is demonstrated. |
| Core services and scheduling | [worker.nix](worker.nix), [worker-pools.nix](worker-pools.nix), [Workers.md](Workers.md), `subservices/` | `A/nix/module.nix`, `A/nix/runtime-environment.nix`, `A/nix/tests/resource_priority_test.nix` | Consolidate reusable Nix unit definitions separately from moving Python behavior. Moving shell from LuxNix into upstream `nix/module.nix` alone does not put a feature in the wheel. |

Wheel mode is already the default. Prioritizing it means completing the installed
command surface, avoiding checkout-dependent runtime behavior, and making one
preparation service responsible for installation. Inventory the existing
`ensure_wheel_runtime_installed` calls before removing them: every web, worker,
maintenance and one-shot entry must still depend on a prepared runtime.
Do not replace this work with a mandatory source-built Nix package. A future
immutable wheel-derived environment is a separate deployment improvement.

## Existing wheel functionality to integrate

### Recovery

- OS implementation: [scripts.nix](scripts.nix), `runLocalDataRecoveryScript`;
  [subservices/lx-annotate-data-recovery.nix](subservices/lx-annotate-data-recovery.nix).
- Existing application implementation: `A/lx_annotate/cli.py:recover_data`,
  `A/lx_annotate/management/commands/recover_runtime_data.py`,
  `A/lx_annotate/services/runtime_recovery.py`,
  `A/lx_annotate/management/commands/repair_managed_payloads.py`.
- Interface: `lx-annotate-recover-data --target PATH --state-file PATH`, repeated
  `--source PATH`, and explicit force/repair controls. Pass existing state and
  marker locations; do not accidentally rerun one-time recovery after upgrade.
- The selected 1.7.2 wheel calls `check_migration_compatibility` before `migrate`;
  the former 1.5.7 blocker is closed. Replacement still needs installed-artifact
  parity for legacy marker/state reuse, interrupted copy, retries, repair gates
  and retained originals. The current generated recovery remains until that
  broader contract is proven; the compatibility check is not a missing feature.
- Keep mount access, unit ordering, service identity and legacy-root policy in
  LuxNix. Move recovery/repair eligibility, state publication and structured
  events into the existing application service using backend atomic wrappers.

### Hub node provisioning

- LuxNix generates topology JSON with secret-file handles and invokes
  `lx-annotate-provision-hub-nodes --require-existing-centers --config PATH`.
  The duplicate generated Python has been removed.
- The selected wheel owns validation and the transaction through
  `lx_annotate/hub/node_provisioning.py` and its management command.
- `tests/lx-annotate/test_installed_node_provisioning.py` installs the digest-bound
  wheel outside source checkouts and proves camelCase inputs, existing-center
  rejection, repeat idempotence, secret rotation and rollback after a later
  failure using real SQLite transactions and lightweight domain API models.
  This is application-command parity, not the backend's full PostgreSQL suite.

### Acceptance and static assets

- OS implementations: [subservices/lx-annotate-preflight.nix](subservices/lx-annotate-preflight.nix),
  [subservices/lx-annotate-acceptance.nix](subservices/lx-annotate-acceptance.nix),
  [scripts/acceptance-static.nix](scripts/acceptance-static.nix),
  [scripts/wheel-static-check.py](scripts/wheel-static-check.py), and
  `config.nix:lx_annotate_wheel_sync_static`.
- Existing application implementations:
  `A/lx_annotate/management/commands/runtime_acceptance.py`,
  `A/lx_annotate/management/commands/verify_encrypted_storage.py`,
  `A/lx_annotate_assets/__init__.py`, `A/lx_annotate/checks.py`.
- Compare `lx-annotate-acceptance --static-root PATH` with both existing units.
  Preserve migration compatibility checking; packaged acceptance also checks
  HLS readiness, so account for startup ordering before enabling it on boot.
- Consolidate Vite validation into the existing standalone assets package.
  Preserve pre-install rejection of invalid wheels, including the OS checker's
  central-runtime-path contract; a post-install CLI alone is not equivalent.
- Keep live HTTPS/TLS probes, required-worker activity checks, Nginx serving
  paths and host permissions in LuxNix.

### Storage relief and terminology

- Storage relief: `config.nix:emergencyStorageReliefScript` and
  [scripts/storage-relief.nix](scripts/storage-relief.nix) already delegate the
  domain operation to `lx-annotate-manage emergency_storage_relief`.
  `A/lx_annotate/cli.py:storage_relief` supplies the packaged console adapter.
  Reuse the backend command; retain external mount/UUID validation in LuxNix.
- Terminology: [subservices/lx-dtypes-kb-bootstrap.nix](subservices/lx-dtypes-kb-bootstrap.nix)
  orders the upstream module's dependency-provided bootstrap after wheel
  preparation. Read `A/nix/module.nix` and
  `A/docs/guides/terminology-delivery.md`. Consolidate remaining registry path
  defaults without recreating registry logic in LX-Annotate.

## Application behavior still embedded in OS configuration

These are extraction work units, not permission to delete existing safeguards.
New command names below are proposals rather than installed interfaces.

| Work unit | Implementation to extract | Application destination or existing API | Required behavior and host residue |
| --- | --- | --- | --- |
| SAP drop handling | `config.nix:sapImportServiceScript`; duplicated `A/nix/module.nix:sapImportScript`; [subservices/lx-annotate-sap-import.nix](subservices/lx-annotate-sap-import.nix) | Extend `A/lx_annotate/cli.py:import_sap` through an application service; the current command converts one input through `import_sap_is_h_zip`. | Package stable-file detection, collision handling, conversion, processed/failed transitions and retry policy. LuxNix retains path/timer triggers and directory grants. Test incomplete ZIPs, concurrent arrivals, repeated runs and failure moves. |
| Legacy duplicate cleanup | `config.nix:dataCleanupScript`, `move_duplicate_tree`; [subservices/lx-annotate-data-cleanup.nix](subservices/lx-annotate-data-cleanup.nix) | Add a typed cleanup service near `A/lx_annotate/services/runtime_recovery.py`, composing backend filesystem APIs. | Move duplicate eligibility, archive collision rules, move/delete operations and audit events. Preserve ciphertext handling and active-root exclusion. LuxNix retains persisting-mount validation and schedule. Existing hub-export cleanup has different semantics and is not a drop-in replacement. |
| Hub backup | [scripts/hub-backup.nix](scripts/hub-backup.nix): `runLocalHubBackupScript`; [subservices/lx-annotate-hub-backup.nix](subservices/lx-annotate-hub-backup.nix) | Add an application service and thin command, e.g. `lx-annotate-hub-backup`; use `A/docs/guides/secure-backup-disaster-recovery.md` as a contract reference. | Preserve pending snapshots, verified checksums/manifests, free-space reserves, database/media publication boundary, atomic latest pointer and retention. Keep database dump creation, credential delivery and mounted destination in LuxNix. Test interrupted publication and restore integrity. |
| Authentication route policy | [scripts/hub-oidc-entrypoint.py](scripts/hub-oidc-entrypoint.py) explicitly validates and installs the compatibility policy before executing a wheel console entrypoint. Failures terminate startup; no global `sitecustomize` or policy `PYTHONPATH` injection remains. | `A/lx_annotate/settings/settings_base.py`, `A/lx_annotate/urls.py`, `A/lx_annotate/api_urls.py`; coordinate with the backend middleware owner. | The referenced backend source has native `NODE_AUTHENTICATED_PATH_PREFIXES`; installed-artifact route/method/transfer-authentication and mTLS parity remains required. Replace the remaining compatibility mutation only with a released application/backend contract, preserving transfer authentication and mTLS. Non-wheel hub transfers are rejected until that contract exists. Test permitted and rejected route/method combinations before removing the bridge. |
| HLS dispatch policy | [scripts.nix](scripts.nix): `runLocalHlsMaterializationScript`; [subservices/lx-annotate-hls-materialization.nix](subservices/lx-annotate-hls-materialization.nix), [subservices/lx-annotate-hls-backfill.nix](subservices/lx-annotate-hls-backfill.nix) | Thin LX-Annotate adapter over installed backend `materialize_video_hls` and `migrate_media_storage`. | Keep processed-before-raw ordering, queued execution, artifact validation and rejection of unsafe force/inline operation in the application contract. LuxNix supplies the unit, timer and resources. Do not duplicate backend materialization algorithms. |
| Runtime and key validation | [scripts.nix](scripts.nix): `runLocalMasterKeyCheckScript`; `config.nix:hubEnvelopeKeyPreflightScript`; [runtime-context.nix](runtime-context.nix), [scripts/env.nix](scripts/env.nix) | Existing `A/lx_annotate/settings/settings_base.py`, `A/lx_annotate/checks.py`, `A/lx_annotate/management/commands/verify_encrypted_storage.py`; backend runtime-path and cryptographic validators. | Centralize application path/default/cryptographic interpretation. Keep secret provisioning, host-specific owner/group checks and mount/device identity at the OS boundary. Application startup must still reject missing, malformed or unusable keys. |
| Worker and monitoring contracts | `config.nix:workerConfigs`, `monitoringConfig`, `ffmpegStreamThrottleScript`; [worker.nix](worker.nix), [worker-pools.nix](worker-pools.nix) | `A/lx_annotate/celery.py`, `A/lx_annotate/monitoring/contracts.py`, `A/lx_annotate/monitoring/service.py`, `A/nix/module.nix` | Application owns task/queue semantics and health interpretation. OS owns concrete unit names, CPU/memory/GPU budgets and cgroup controls. Preserve web priority and aggregate background limits; do not move privileged `systemctl` operations into web code. |

## Verification files to carry into implementation

| Area | LuxNix regression references | LX-Annotate regression references |
| --- | --- | --- |
| Installation and dependency authority | `L/tests/lx-annotate/test_lx_annotate_wheel_runtime_install.py`, `test_wheel_downgrade_guard.py`, `test_lx_annotate_nix_eval_contract.py` in the same directory | `A/tests/system/test_migration_compatibility.py`, `A/tests/system/test_migration_history_safety.py`, `.github/workflows/wheel-testpypi.yml` in A |
| Operational command parity | `L/tests/lx-annotate/test_lx_annotate_data_recovery_repair_gate.py`, `test_lx_annotate_nix_eval_contract.py` | `A/tests/system/test_operational_commands.py`, `A/tests/system/test_operational_command_boundaries.py`, `A/tests/system/test_center_node_provisioning.py`, `A/tests/storage/test_data_dir_migration.py` |
| Static and acceptance | `L/tests/lx-annotate/test_wheel_static_check.py`, `test_lx_annotate_static_acceptance.py` | `A/tests/system/test_static_assets_contract.py`, `A/tests/system/test_operational_commands.py` |
| Storage and backup | `L/tests/lx-annotate/test_persisting_storage_contract.py`, `test_encrypted_data_mount.py`; `L/tests/nixtest/lx_annotate_hub_backup_vm_test.nix` | `A/tests/hub/test_storage_recovery.py`, `A/tests/storage/test_data_dir_migration.py`; add command-level backup and legacy cleanup tests beside their new owners |
| Intake and environment | `L/tests/lx-annotate/test_lx_annotate_nix_eval_contract.py`, `test_lx_annotate_terminology_contract.py` | `A/tests/ingestion/test_packaged_watcher_acceptance.py`, `A/tests/system/test_secretspec_environment_contract.py`, `A/tests/system/test_environment_checks.py` |
| HLS, workers and monitoring | `L/tests/lx-annotate/test_hls_startup_ordering.py`, `test_lx_annotate_worker_shape.py`, `test_lx_annotate_monitoring_contract.py` | `A/tests/system/test_admin_monitoring.py`, `A/tests/system/test_production_celery_redis_recovery.py`, `A/nix/tests/resource_priority_test.nix` |

## Implementation order and acceptance criteria

1. Complete the wheel executable surface and release smoke tests first. Keep
   `runtime.mode = "wheel"` as the production default, with an explicit supported
   package-mode boundary. Avoid a second installer or dependency-version map.
2. Close parity gaps in existing packaged commands, then replace generated
   recovery, provisioning and application-acceptance implementations one at a
   time. Delete the superseded code in the same change that adopts its owner.
3. Extract SAP orchestration, legacy cleanup and backup as application services
   with thin CLI adapters. Resolve authentication policy with the backend owner.
4. Consolidate application configuration and queue contracts; reduce repeated
   core unit definitions through the upstream Nix module. Keep fleet policy in
   inventory. Retire repo-mode/checkout-specific paths only after their remaining
   consumers have a tested wheel replacement.
5. Build the release wheel and install it in an isolated environment from an
   unrelated working directory. Verify the entry points, installed dependency
   metadata and packaged assets; then exercise operations against disposable
   data and a disposable database. No development checkout may satisfy imports.
6. Run the affected LuxNix regression files and NixOS integration/VM checks.
   Preserve missing-mount/key failure, downgrade rejection, interrupted install
   behavior, migration compatibility, mTLS and encrypted storage. Compare the
   effective units/environment before and after; deployment is a separate step.

Successful extraction reduces independently maintained application algorithms,
defaults and schemas. Moving a script to another Nix file, adding a parallel CLI
implementation, or accepting a wrapper that still imports a checkout does not
meet that criterion. Entry-point inventory and source inspection in this handoff
are not execution or production-readiness evidence.

Operational references: [LuxNix deployment guide](../../../../docs/deployment-guide.md),
[service deployment](../../../../docs/deploying-services-lx-annotate-style.md),
[database ownership](../../../../docs/database-ownership.md),
`A/docs/guides/deployment-strategy.md`, `A/docs/guides/wheel-deployment.md`, and
`A/feature-tracking/DeploymentSourceHygiene.yml`. Readiness remains in the
existing feature trackers; this document does not create a second tracker.

## Reproduce release-specific parity

Set `LX_ANNOTATE_PARITY_WHEEL` to the realized selected wheel, then run:

```bash
uv run --with django==6.0.3 --with celery==5.6.3 --with pydantic==2.14.2 pytest -q tests/lx-annotate/test_installed_node_provisioning.py
```

The explicit lane fails if the wheel digest differs. Ordinary root discovery
skips it when no artifact is supplied. For a release change, select the hash-pinned
`runtime.wheelPath`. Its packaged metadata is the dependency source of truth;
an unrelated source checkout or independently maintained catalog must not replace it.
The default online preparation waits for `network-online.target`. For an explicit
offline deployment, provide a compatible `runtime.wheelhousePath` containing the
required dependency artifacts and any configured overrides. The runtime stamp
binds the application digest, interpreter, wheelhouse contents, overrides and
installer revision. Default online resolution does not provide a complete hashed
transitive dependency lock; retain that distinction when assessing reproducibility.
