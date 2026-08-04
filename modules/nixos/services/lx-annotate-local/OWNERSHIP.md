# LX-Annotate deployment ownership and overlap inventory

This is a working inventory for reducing this LuxNix module. It records where
deployment logic is currently implemented twice, or where application logic is
still embedded in LuxNix even though it can be shipped and tested with
`lx-annotate`.

The intended boundary is:

- LuxNix creates users, mounts, directories, secret files, and systemd units.
- LuxNix selects host policy and passes it to the units as environment variables
  or command-line arguments.
- The installed `lx-annotate` package owns application defaults, validation,
  migrations, data operations, and executable entry points.
- A service must not depend on a source checkout, `devenv`, or scripts generated
  from the deployment module in wheel mode.

This document is an inventory, not proof that an item is ready to delete. Remove
a LuxNix implementation only after the corresponding command and its tests are
present in the deployed `lx-annotate` package.

## Runtime path overlaps

| Runtime path | LuxNix source | LX-Annotate source | Target owner |
| --- | --- | --- | --- |
| Protected data root (`/var/lib/lx-annotate/data`) | `runtime-context.nix`: `runtimeDataRootPath`; `scripts/env.nix`: `LX_ANNOTATE_ENCRYPTED_DATA_DIR` | `nix/module.nix`: `effectiveEncryptedDataDir`; `nix/runtime-environment.nix`: `mkAppOwnedEnvironment` and `mkHostOwnedEnvironment` | LuxNix creates/mounts it and passes `LX_ANNOTATE_ENCRYPTED_DATA_DIR`; LX-Annotate derives all children. |
| Storage root (`<data>/storage`) | `runtime-context.nix`: `runtimeStorageRootPath`; `scripts/env.nix`: `STORAGE_DIR`, `PROTECTED_MEDIA_ROOT` | `nix/runtime-environment.nix`: `storageEnvironment`; Django settings consume the variables | LX-Annotate derives the path; LuxNix only creates the directory required before startup. |
| Streamable video tree (`storage/streamable_videos/{raw,processed}`) | `runtime-context.nix`, `scripts/env.nix`, `config.nix` tmpfiles, and several wrappers in `scripts.nix` | `nix/runtime-environment.nix`: `storageEnvironment`; application storage settings and management commands consume it | LX-Annotate derives and validates; LuxNix creates the three directories and exports only an override if a host needs one. |
| Terminology tree (`terminology/{registry.json,packages}`) | `runtime-context.nix`, `options.nix`, `config.nix` tmpfiles and `terminologyBootstrapScript` | `nix/runtime-environment.nix` exports both terminology paths; `nix/module.nix` also creates the tree; `lx_dtypes` provides registry commands | LX-Annotate/lx-dtypes owns defaults, bootstrap, and validation; LuxNix creates the directories and passes optional path overrides. Do not create a placeholder registry in two modules. |
| Intake tree (`import/{video_import,report_import,preanonymized_import,sap_*}`) | `runtime-context.nix`, `options.nix`, `config.nix` tmpfiles, watcher and SAP wrappers | `nix/module.nix` owns watcher/SAP paths and units; `lx_annotate.cli` exposes `watch` and `import_sap` | LuxNix creates configured intake directories and exports their paths. The package owns scanning, stability checks, import, and processed/failed transitions. |
| Static assets (`/var/lib/lx-annotate/staticfiles` and wheel-local `staticfiles`) | `runtime-context.nix`, `scripts/frontend-assets.nix`, wheel web wrapper in `scripts.nix` | packaged `lx_annotate/static*`, `docs/guides/asset-deployment.md`, Django production settings | The bundle must contain a valid, immutable asset tree and manifest. LuxNix creates the serving directory or points nginx directly at a package output; it must not synthesize a manifest. |
| Application config (`<wheel>/conf`, service-user `config`, `.env.systemd`) | `runtime-context.nix`, `scripts/env.nix`, `runtimeEnvScript`, runtime shell library | `secretspec.toml`, `lx_annotate/settings/config.py`, file-backed secret support | LuxNix owns secret material and an optional systemd `EnvironmentFile`. LX-Annotate owns parsing/defaults. Compatibility copies and generated secretspec configuration should disappear with repo mode. |
| Wheel environment (`<service-home>/lx-annotate-wheel/.venv`) | `runtime-context.nix` and `ensure_wheel_runtime_installed` in `scripts.nix` | `package.nix`, `flake.nix`, `pyproject.toml` | Prefer a hermetic Nix package output from LX-Annotate. Runtime virtualenv creation and pip installation should not be a boot-time LuxNix responsibility. |
| Hub backup tree (`hub/backup/{incoming,snapshots,manifests}`) | `runtime-context.nix`, `options.nix`, `scripts/hub-backup.nix`, `config.nix` | backup/recovery policy is documented in `docs/guides/secure-backup-disaster-recovery.md`; application data contracts live in LX-Annotate/endoreg-db | LuxNix creates/mounts destinations and schedules a command. A packaged command must own snapshot manifests, exclusions, retention, and verification. |
| Cleanup/archive trees | `runtime-context.nix`, `options.nix`, cleanup and storage-relief scripts | hub cleanup policy and typed storage operations already live under `lx_annotate/hub`; data migration delegates to endoreg-db | LuxNix supplies external mount paths and scheduling. Eligibility, manifests, copy verification, and deletion policy belong in a packaged, typed command. |

## Source-path overlaps already present

These pairs can be consolidated without inventing a new application interface:

| LuxNix path | Existing LX-Annotate path | Overlap |
| --- | --- | --- |
| `scripts/env.nix` | `nix/runtime-environment.nix` | Both classify and render the runtime environment, including identical storage and streamable-video paths. LuxNix should provide host-owned values to the upstream environment constructor instead of maintaining a second app-owned contract. |
| `config.nix` core service definitions | `nix/module.nix` | Both define web, migrate, base-data, watcher, SAP import, frame export, Celery workers, timers, tmpfiles, users, dependencies, and service hardening. LuxNix already uses the upstream module for the web unit; the remaining core units should follow it. |
| `scripts.nix` wheel web/migrate/base-data/watcher/worker/export wrappers | `lx_annotate/cli.py`, `[project.scripts]` in `pyproject.toml`, and `nix/module.nix` | The bundle already exposes `lx-annotate-web`, `-manage`, `-migrate`, `-load-base-data`, `-worker`, `-watch`, `-export-frames`, and `-import-sap`. Systemd can execute these directly. |
| `scripts.nix` SAP stability loop | `nix/module.nix` `sapImportScript` | The same loop and processed/failed movement exist in both Nix repositories. It should become one packaged LX-Annotate command, while the Nix module only supplies directories and trigger policy. |
| `scripts.nix` master-key and acceptance Django checks; `config.nix` acceptance unit | `lx_annotate/checks.py`, `lx_annotate/management/commands/verify_encrypted_storage.py`, and `deployment_example/acceptance-smoke.sh` | Application checks already exist, but orchestration is duplicated. Add one installed health/acceptance entry point; keep only host reachability and `systemctl` assertions in LuxNix if required. |
| `scripts.nix` data recovery implementation | `scripts/migrate_data_dir.py`, `repair_managed_payloads`, and the upstream `migrate_data_dir` management command | Migration semantics and payload repair are application/domain logic and must be bundled. LuxNix should pass legacy roots, target root, state/manifest path, and dry-run policy. |
| `scripts/frontend-assets.nix` and wheel static synchronization | packaged static files and `docs/guides/asset-deployment.md` | Manifest parsing, fallback manifest generation, and locating package assets are release-contract concerns. The package build should fail if its asset contract is incomplete. |
| `config.nix` `hubNodeProvisioningPython` | LX-Annotate/endoreg-db `NetworkNode` models and management-command layer | Database model validation and idempotent node provisioning belong in an audited management command. LuxNix should pass a JSON config path plus file-backed secrets. |
| `config.nix` terminology bootstrap shell | `lx_dtypes` registry CLI and LX-Annotate terminology API | Selecting the bundled default and validating registry contents is bundle logic. LuxNix should only provide registry/import paths and schedule the packaged command when needed. |
| `scripts.nix` HLS argument validation and dispatch | LX-Annotate management commands for `migrate_video_streamable_storage` and `materialize_video_hls` | Argument policy, default artifact kinds, and safety rejection belong in the console/management command. LuxNix should configure a unit and timer. |
| `scripts.nix` cleanup/storage relief and `scripts/hub-backup.nix` | typed storage and hub policy in LX-Annotate/endoreg-db | File eligibility, manifests, hashes, retention, and mutation safety are domain logic. Only mount checks, paths, resource controls, and scheduling remain host-owned. |
| `scripts.nix` repo sync/build/bootstrap path | LX-Annotate `flake.nix`, `package.nix`, release workflow, and packaged assets | Production should consume an immutable package. Clone, reset, `devenv`, Makefile, frontend build, and last-known-good checkout logic are repo-mode deployment concerns and can be removed once repo mode is retired. |

## Operational commands awaiting a release gate

The development checkout contains an initial implementation of these proposed
entry points. They are not part of the configured published wheel yet and no
LuxNix runtime implementation may be removed or replaced on their behalf:

| Command | Packaged implementation | LuxNix residue |
| --- | --- | --- |
| `lx-annotate-recover-data` | Idempotent migration, compatibility overlay through typed atomic copies, upload-job cleanup reconciliation, payload repair, and atomic state markers | Pass target, legacy source roots, state path, service ordering, and mount access. |
| `lx-annotate-bootstrap-terminology` | Registry provisioning, active-identity validation, packaged-bundle smoke test, and best-effort policy | Pass registry path and optional initial-bundle identity/path; schedule before base-data loading. The published 0.9.54 variant exists, but cannot yet express the complete configured `initialBundle` contract. |
| `lx-annotate-provision-hub-nodes` | Pydantic-validated topology JSON, transactional model updates, and file-backed shared-secret rotation | Render the topology JSON and grant read access to secret files. |
| `lx-annotate-storage-relief` | Delegates to the packaged endoreg-db typed storage-relief command, which owns eligibility, atomic copy/move/delete, verification, JSON logs, and manifests | Verify the external host mount/device identity and pass the generated policy JSON. |
| `lx-annotate-acceptance` | Django critical checks, encrypted-storage verification, HLS readiness, and packaged Vite manifest/asset validation | Keep live TLS/HTTP probing and required-systemd-worker checks. |

Current release evidence: LuxNix resolves the published
`lx_annotate-0.9.54-py3-none-any.whl` with the SRI hash configured in
`options.nix`. The wheel's actual `entry_points.txt` contains
`lx-annotate-bootstrap-terminology`, but none of the other four commands. The
published terminology command only supports the packaged default module; it
does not support the configured explicit input directory, version, and medical
field accepted by LuxNix's `runtime.terminology.initialBundle` option. The
release workflow contains an installed-wheel terminology smoke test, but no
package-only NixOS VM test has yet exercised the complete LuxNix unit against
this exact published wheel. Consequently none of the five LuxNix
implementations is currently removable.

The published release comparison uses commit
`213a8e2d1e2b15388f126aa62fb0c128a5baa5c7` from
`/home/admin/release-worktrees/lx-annotate-0.9.54`. Release work for 0.9.55 is
being prepared separately from that published base. The mixed
`/home/admin/dev/lx-annotate` worktree is a candidate implementation source,
not release or deployment evidence.

## Deletion and retention matrix

This matrix records the intended edit only after the exact published-wheel and
package-only VM gates pass.

| Capability | Delete or reduce after the gate | Retain in LuxNix |
| --- | --- | --- |
| Recovery | Delete the application recovery implementation in `scripts.nix` (`runLocalDataRecoveryScript`), including migration fallback, compatibility copying, repair orchestration, and state-marker semantics. Point the unit at `lx-annotate-recover-data`. | `dataRecovery` host paths/options, the systemd unit, mount/write access, ordering, legacy-source paths, target path, and state-file path. |
| Terminology bootstrap | Delete `terminologyBootstrapScript` from `config.nix` and invoke `lx-annotate-bootstrap-terminology` with the registry and optional explicit bundle arguments. | Terminology directories/tmpfiles, environment paths, optional initial-bundle selection, best-effort unit policy, and load-base-data ordering. |
| Hub provisioning | Delete `hubNodeProvisioningPython` and `hubNodeProvisioningScript` from `config.nix`; invoke `lx-annotate-provision-hub-nodes --config ...`. | `hubNodeProvisioningData`, topology options, file-backed secret paths/credentials, database/service ordering, and unit hardening. |
| Storage relief | Replace only the application-command tail of `emergencyStorageReliefScript` with `lx-annotate-storage-relief --config ...`; do not delete its host checks. | `emergencyStorageReliefConfig`, mountpoint/device/UUID verification, external mount dependencies, writable paths, scheduling, and resource controls. |
| Acceptance | Replace Django checks owned by the application with `lx-annotate-acceptance`; remove duplicated app-level checks only. | The acceptance systemd unit, required-worker `systemctl` checks, live nginx/TLS HTTP probe, certificate selection, ordering, and mount access. |

Until the gate passes, all rows above are classification only. In particular,
the presence of a management command or a command in the development checkout
does not authorize deletion of its LuxNix counterpart.

The remaining packaged-command candidates are:

1. `lx-annotate-prepare-runtime`: validate the passed root paths and report the
   expected directory contract without creating host mounts or changing host
   ownership.
2. `lx-annotate-hub-backup`: own typed snapshot manifests, verification, and
   retention while LuxNix supplies mounted source/destination paths.
3. `lx-annotate-import-sap-drops`: own stable-file detection and success/failure
   transitions, not just conversion of one ZIP.

Every filesystem-mutating application command must preserve the repository's
typed filesystem-wrapper, atomic-write, and structured-logging requirements.

## Host-owned residue

The reduced LuxNix module should retain only work that needs host authority or
host topology:

- user, group, supplementary groups, directory owner/mode, and `tmpfiles`;
- LUKS device opening/closing, mount dependencies, and Vault-provided files;
- nginx virtual host, TLS/mTLS proxy policy, and protected-media offload;
- PostgreSQL/Redis selection and ordering, without duplicating application
  validation;
- systemd unit enablement, timers/path triggers, restart policy, sandboxing,
  resource limits, GPU assignment, and network/mount dependencies;
- file-backed secrets and certificates, passed by path rather than copied into
  application configuration;
- external archive mount identity checks where only the host can establish the
  mount/device relationship;
- environment values that select host policy or name host paths.

Application-owned defaults such as queue names, storage subdirectory names,
settings modules, storage profiles, and command names should not be repeated in
LuxNix.

## Proposed reduction order

1. Make the upstream `nix/module.nix` and `nix/runtime-environment.nix` the only
   definitions of core units and app-owned environment values.
2. Replace wheel shell command strings and the boot-time virtualenv with direct
   references to a hermetic LX-Annotate package output.
3. Publish the missing packaged commands, prove them through package-only Nix
   and VM tests, and only then switch LuxNix units to call them directly.
4. Delete repo-mode sync/build/bootstrap logic and its checkout-specific paths.
5. Collapse `runtime-context.nix` to host paths and `scripts/env.nix` to
   host-owned environment values, then remove compatibility environment files.
6. Remove duplicated options after all consumers use the upstream module or a
   packaged command.

## Verification gate for each move

For every migrated item:

- the command is present in the built package, not only in the checkout;
- the command is present in the exact published wheel selected by
  `runtime.wheelPath`, verified from wheel metadata;
- package tests cover path derivation and failure behavior;
- console-script and Django management-command adapters stay thin; validation,
  model mutation, transactions, and recovery policy live in an application
  service layer instead of in the deployment adapter;
- the NixOS VM test starts the unit using only the package plus passed
  environment/file paths;
- tests must not read, import, or execute `/home/admin/dev/lx-annotate` to make
  the wheel contract appear satisfied;
- no unit invokes `devenv`, a Makefile, pip, or a checkout path;
- a missing mount, secret, or required path still fails closed;
- removal decreases duplicated options/scripts rather than adding another
  compatibility layer.
