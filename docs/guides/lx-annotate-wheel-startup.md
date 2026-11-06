# LX-Annotate wheel startup

**Schema version:** 1

**Service:** `lx-annotate-wheel-runtime.service`

**Owner:** `modules/nixos/services/lx-annotate-local`

**Risk:** remote-read-only

## Startup contract

- The preparation unit is the sole package installer for the shared virtual environment.
- Preparation validates and synchronizes packaged static assets before it succeeds, including when the wheel is already installed. A failed copy or asset check blocks dependent startup and is retried on the next preparation attempt.
- Web and worker entrypoints verify the prepared release without recopying the static tree. Web process restarts therefore avoid recursive asset copying and permission updates. If served assets are damaged or removed, rerun preparation through the reviewed recovery workflow; a web restart alone does not repair them.
- Online installations wait for network-online.target; an explicit wheelhouse does not add this dependency.
- Application and override plans must both resolve and pass downgrade admission before either install starts.
- Resolver failure leaves installed distributions and the successful release stamp unchanged.
- Diagnostics expose a fixed category and narrowly validated missing requirements, never raw pip output or authenticated URLs.
- Network-online ordering does not guarantee that a package index is reachable or contains a requested release.

## Storage during the root-encryption transition

With `storage.operatorUnlocked.layout = "boot-luks"`, startup and activation
validate the configured filesystem graph and the encrypted backing of each
protected path. They do not inspect legacy container files or scan retired
container/bind mount locations. Keeping or removing the old `volumes` and
`bindMounts` migration metadata does not change those gates.

Root device identity, LUKS2, Btrfs members, secondary disks and keys remain
checked. An unencrypted application path still blocks startup. Existing
explicit `legacy-containers` hosts retain their layout-specific checks until
migration; this change neither selects a new layout nor migrates or removes data.
Migration acceptance and container retirement remain explicit operator work.

## Catalogue reconciliation

**Service:** `lx-annotate-load-base-data.service`

### Command

```bash
lx-annotate-load-base-data --reconcile-legacy
```

**Order:** Prepared runtime and Django schema migrations, then base-data reconciliation, then key verification and web startup.

### Behavior

- The application provisions the governed registry through its normal base-data loader.
- Fresh or equivalent catalogues use strict import; the known seven colorectal indication conflicts receive the bounded migration.
- Dependency creation, relationship changes and reconciliation commit atomically; existing IDs and patient links are preserved.
- Repeated service runs recheck the database and reuse import receipts without duplicate records or filesystem success stamps.
- Unexpected conflicts and missing command support fail the unit and block dependent startup.

**Release requirement:** Install an endoreg-db artifact implementing load_base_db_data --reconcile-legacy together with this LuxNix change; older packages reject the flag.

**Preview:** lx-annotate-load-base-data --reconcile-legacy --dry-run

**Scope:** Shared base-data service in wheel and repository modes, plus the repository migration helper. Legacy custom runtime.commands overrides remain operator-owned.

## Read only admission

**Script:** `modules/nixos/services/lx-annotate-local/scripts/wheel-downgrade-guard.py`

**Invocation:** `<runtime-venv>/bin/python <guard.py> --wheel <canonical-wheel-path> --expected-version <release-version> --check-only`

**Optional overrides:** `--overrides-json '<JSON list matching runtime.wheelDependencyOverrides>'`

**Offline arguments:** `-- --no-index --find-links <approved-wheelhouse>`

### Notes

- Use the same interpreter, package index and wheelhouse configuration as the preparation unit.
- A Nix-store wheel filename with a store-hash prefix must first be staged under its canonical wheel filename in a private review directory.
- Check-only resolves dependencies but writes no constraints and installs no packages; pip may download/cache candidates and prepare build metadata.
- Use PIP_NO_CACHE_DIR=1 to avoid persistent pip cache writes during investigation.
- Avoid inherited development-shell LD_LIBRARY_PATH, LD_PRELOAD, PYTHONHOME and PYTHONPATH; they can load libraries from an unrelated checkout.
- A successful check is admission evidence, not proof that installation, migrations or application startup will succeed.

## Failure categories

**Distribution unavailable:** Check requested release publication, wheel Python/platform compatibility and index or wheelhouse contents.

**Dependency conflict:** Build a release with compatible constraints; do not bypass dependency resolution.

**TLS verification failed:** Repair the package-index trust configuration without disabling TLS verification.

**Index unreachable:** Inspect DNS, network availability and proxy configuration before retrying.

**Storage full:** Inspect runtime cache and temporary storage capacity before preparing packages.

**Permission denied:** Inspect service-user access to wheel inputs, cache and runtime directories.

**Resolver error:** Inspect release inputs in a private operator session; do not copy raw resolver output into shared logs.

## Incident

**Host:** gc-02

**Observed at:** 2026-09-28T11:47:57+02:00

**Selected application:** `lx-annotate==1.3.13`

**Missing requirement:** `endoreg-db==1.3.15`

**Pip visible index maximum at investigation:** `endoreg-db==1.3.14`

### Publication verified

**Source:** `https://pypi.org/pypi/endoreg-db/1.3.15/json`

**Wheel uploaded at:** `2026-09-28T08:02:10.606249Z`

**Sdist uploaded at:** `2026-09-28T08:02:12.905301Z`

**Requires python:** `<3.13,>=3.12`

**Yanked:** `false`

### Index response discrepancy

**Endpoint:** `https://pypi.org/simple/endoreg-db/`

**Method:** Same runtime Python 3.12.12 and pip PipSession, JSON Accept header, Cache-Control no-cache; vary only Accept-Encoding.

#### Identity

**Last serial:** 41542001

**Includes 1 3 15:** `true`

#### Gzip

**Last serial:** 41444057

**Includes 1 3 15:** `false`

#### Gzip deflate

**Last serial:** 41444057

**Includes 1 3 15:** `false`

**Interpretation:** A stale compressed response is served on the index request path; the responsible cache layer is not established.

**Pip reproduction:** Both default configuration and explicit PyPI with PIP_CONFIG_FILE=/dev/null fail no-deps dry-run admission for endoreg-db==1.3.15, with --no-cache-dir.

**Installed application:** `lx-annotate==1.3.12`

**Installed backend:** `endoreg-db==1.3.14`

**First failed stage:** Wheel candidate resolution, before package installation or migration.

### Additional observations

- Pip reported invalid-distribution remnants in the shared environment. No deletion or repair was attempted.

## Recovery

- For this incident, do not upload again or change the release version solely to address visibility; both release artifacts already exist on PyPI.
- Restore fresh compressed index responses, or provision an approved wheelhouse containing the selected release and its complete dependencies, verifying artifacts against PyPI release hashes.
- Do not permanently monkeypatch pip HTTP headers to hide an unresolved index-cache issue.
- Run check-only admission for the complete selected release before activation.
- Do not substitute a lower dependency with --no-deps, weaken the downgrade guard, or delete the successful release stamp.
- After an explicitly authorized deployment, run the ordered preparation, migration, base-data, key and application gates documented in Diagnostics.md.
- Confirm the final acceptance unit and worker health before declaring recovery.

## Verification

### Focused tests

#### Command

```bash
.devenv/state/venv/bin/pytest tests/lx-annotate/test_wheel_downgrade_guard.py tests/lx-annotate/test_lx_annotate_wheel_runtime_install.py -q
```

**Result:** 36 passed, including rendered gc-02 guard and online/offline unit ordering.

### Host evaluation

#### Command

```bash
nix eval --raw '.#nixosConfigurations.gc-02.config.system.build.toplevel.drvPath'
```

**Result:** Passed; an unrelated optional CUDA binary-cache request emitted HTTP 401.

### Documentation

#### Command

```bash
devenv tasks run docs:check
```

**Result:** `Passed.`

### Other checks

- Focused Ruff, nixfmt --check and git diff --check passed.
- Feature tracker validation passed; environment lifecycle readiness remains incomplete (2 of 8 criteria verified).

**Live admission:** Check-only reproduced distribution_unavailable for endoreg-db==1.3.15 without installing packages or writing constraints.

**Not performed:** Activation, service restarts, package installation, migrations, invalid-distribution cleanup, and full NixOS system build.

## Static preparation verification (2026-11-06)

Commands run from the repository root:

```bash
.devenv/state/venv/bin/python -m pytest -q tests/lx-annotate/test_lx_annotate_wheel_runtime_install.py tests/lx-annotate/test_wheel_static_check.py tests/lx-annotate/test_lx_annotate_switch_lifecycle.py --tb=short
.devenv/state/venv/bin/python -m pytest -q tests/test_documentation_contract.py
nix build --no-link --impure --expr 'let f = builtins.getFlake "git+file:///home/admin/luxnix"; in f.nixosConfigurations.gc-10.config.services.lx-annotate.package'
python scripts/lint_structure.py
git diff --check
```

Results: 64 startup/static/lifecycle tests and 26 documentation tests passed;
the gc-10 runtime package built; 23 structure manifests and whitespace checks
passed. Pytest reported cleanup warnings for unrelated temporary directories.
The broader run including encryption-default and file-mover contracts had
87 passes and 10 failures: one existing installer source expectation and nine
storage evaluations failing on missing `retainContainers`. The same attribute
blocked `nix eval --raw '.#nixosConfigurations.gc-02.config.system.build.toplevel.drvPath'`.

`devenv tasks run docs:check` and `devenv tasks run nix-quality:check` stopped
at the Secretspec reason policy; the underlying commands were run directly.
`.devenv/state/venv/bin/python scripts/nix-quality.py` passed parse, formatting,
Statix and flake-checker checks, but failed source visibility and Deadnix on
the unrelated untracked `tests/nixtest/in_place_encryption_vm_test.nix`.
`./feature-tracking/tracker.py validate` passed all 11 definitions;
`./feature-tracking/tracker.py check lx_annotate_environment_lifecycle_audit`
remained nonzero at 2/10. These blockers were not changed or waived.
No activation, full system build or production uptime measurement was performed.

## Root-storage gate verification (2026-11-06)

```bash
.devenv/state/venv/bin/python -m pytest -q tests/test_boot_storage.py tests/test_operator_unlocked_storage.py tests/test_managed_secret_storage.py --tb=short
nix eval --raw '.#nixosConfigurations.gc-02.config.system.build.toplevel.drvPath'
.devenv/state/venv/bin/python -m pytest -q tests/test_documentation_contract.py
python scripts/lint_structure.py
```

All 126 storage tests passed (one warning), including fleet boot-layout checks,
legacy-layout coverage, and gc-02/gc-10/gs-02 root-mode independence from legacy
container metadata. gc-02 system evaluation, 26 documentation tests and all
23 structure manifests passed. No full system build, VM boot or activation was
performed; these results do not establish deployed fleet encryption.

The Devenv documentation and Nix-quality wrappers still stop at the Secretspec
reason policy. The direct Nix-quality runner passes parsing, Deadnix, Statix,
formatting and flake-checker, but flags the unrelated untracked in-place VM test.
The direct Python-quality runner reports 71 existing diagnostics outside the
changed code. Changed-file whitespace checks pass; the repository-wide check
reports an unrelated trailing blank line in gc-09 inventory. Tracker validation
passes; environment lifecycle readiness remains incomplete at 2/10.
