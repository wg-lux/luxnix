# LX-Annotate wheel deployment and application ownership handoff

Make the reviewed LX-Annotate wheel the primary production artifact. Move
application behavior out of LuxNix-generated Python and shell into installed
LX-Annotate commands. Keep host provisioning and systemd integration in LuxNix.
This handoff identifies implementation sources, existing application equivalents,
remaining gaps, and the tests required before deleting an OS implementation.

## Source and artifact reference points

References were collected on 2026-10-21 from dirty working trees; commit IDs
identify their bases, not immutable copies of the uncommitted changes:

- `L/` means the LuxNix repository, `/home/admin/luxnix`, based on
  `cda962d31bda2811cecdeaeb413c6c84f8a0063e`.
- `A/` means the LX-Annotate repository, `/home/admin/dev/lx-annotate`, based on
  `4937f274d7daef12439fceb006581432141de1d7`. Its working `pyproject.toml`
  declares application `1.5.8` and `endoreg-db==1.5.8.dev1`; this checkout is
  implementation context, not the selected deployment artifact.
- LuxNix selects `lx_annotate-1.5.7-py3-none-any.whl` in
  [options/runtime.nix](options/runtime.nix), `runtime.wheelPath`, with SRI
  `sha256-lDL1JGOdG6Oyf8YL2WqGp1ENs69gZ8HIiv3NAxaq/ZE=`. The downloaded
  artifact matched that digest. Its `METADATA` requires `endoreg-db==1.5.7`.
- Its `entry_points.txt` contains `lx-annotate-recover-data`,
  `lx-annotate-provision-hub-nodes`, `lx-annotate-storage-relief`,
  `lx-annotate-acceptance`, and `lx-annotate-check-static`. Corresponding
  recovery, provisioning, acceptance and asset-check modules are in the wheel.
  Command presence does not establish behavior parity or migration safety.
- `lx-annotate-bootstrap-terminology` is absent from this wheel. The current
  integration uses the dependency-owned `lx-dtypes-kb-registry bootstrap`
  command; do not revive the obsolete bootstrap implementation described in
  earlier versions of this document.

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
- Gap: `_heavy_recovery` in the inspected wheel calls `migrate` without calling
  `check_migration_compatibility`. The LuxNix wrapper currently performs that
  check. Preserve it through a tested application-owned gate before replacement.
- Keep mount access, unit ordering, service identity and legacy-root policy in
  LuxNix. Move recovery/repair eligibility, state publication and structured
  events into the existing application service using backend atomic wrappers.

### Hub node provisioning

- OS implementation: [config.nix](config.nix), `hubNodeProvisioningData`,
  `hubNodeProvisioningPython`, `hubNodeProvisioningScript`;
  [subservices/lx-annotate-hub-node-provisioning.nix](subservices/lx-annotate-hub-node-provisioning.nix).
- Existing application implementation:
  `A/lx_annotate/management/commands/provision_hub_nodes.py`,
  `A/lx_annotate/hub/node_provisioning.py` (`HubNodeSpec`, `provision_hub_nodes`).
- The selected 1.5.7 wheel creates missing centers; LuxNix rejects them. Keep
  the OS implementation until a released wheel supports the explicit
  `--require-existing-centers` application policy. Then replace
  `manage shell < generated.py` with
  `lx-annotate-provision-hub-nodes --require-existing-centers --config PATH`
  after JSON-alias, transaction and secret-rotation parity tests. Keep topology
  JSON generation and file permissions in LuxNix; never put secret contents in
  that JSON.

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
| Authentication route policy | `config.nix:hubOidcMiddlewarePolicy` injects `sitecustomize.py` and mutates `endoreg_db.authz.middleware.PUBLIC_PREFIXES` through `PYTHONPATH`. | `A/lx_annotate/settings/settings_base.py`, `A/lx_annotate/urls.py`, `A/lx_annotate/api_urls.py`; coordinate with the backend middleware owner. | Replace runtime monkey-patching with a supported application/backend authentication contract. A public OIDC exception must still require the intended transfer authentication and mTLS. Test permitted and rejected route/method combinations before removing the patch. |
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
