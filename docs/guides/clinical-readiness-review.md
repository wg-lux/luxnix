# Clinical readiness review

This record preserves the findings and verification reported for the source
revisions and dates below. Conversion to Markdown does not revalidate runtime
state or resolve recorded blockers.

**Schema version:** 1

## Review

**Date:** 2026-09-09

**Repository:** luxnix

**Base commit:** 469620aa86e8f326bb200cf07fff485081e3b6f8

**Checkout state:** Includes pre-existing uncommitted monitoring and gc-02 protection changes.

**Verdict:** `not_ready_for_hostile_clinical_release`

**Scope:** Repository-owned infrastructure, storage data plane, inventory parsing, deployment contracts, quality gates, and MCP verification freshness. This review does not establish clinical diagnostic accuracy or certify a deployed environment. No deployment, secret rotation, migration, clinical data processing, or deliberate resource-exhaustion operation was performed.

**Readiness source:** feature-tracking

**Interpretation:** This is an evidence review, not a parallel completion tracker. Existing feature criteria remain authoritative. A passing source test or lint baseline cannot replace packaged integration tests and live acceptance.

## Findings

### Direct clinical media serving bypasses application authorization

**Id:** CLIN-001

**Severity:** high

**Title:** Direct clinical media serving bypasses application authorization

**Status:** `remediation_blocked_by_concurrent_edit`

#### Evidence

- `modules/nixos/services/lx-annotate-local/config.nix:2464`
- `modules/nixos/services/lx-annotate-local/runtime-context.nix:36`
- `modules/nixos/services/lx-annotate-local/runtime-context.nix:80`

**Impact:** A client able to reach the public vhost and guess a readable path can request files under the protected data root through the direct /media/ alias without passing Django object authorization.

**Proposed fix:** Replace only the /media/ alias with return 404. Preserve the internal /protected_media/ X-Accel-Redirect path and application video routes.

**Coordination:** config.nix is locked by codex-nvenc-gc10; coordination requests were sent. Do not overwrite its unrelated monitoring changes.

**Acceptance:** Verify denied direct requests and unauthorized object access, successful authorized playback, and protected-path denial in the deployed release. Compatibility observed in a sibling source checkout is not release proof.

### Idle TLS peer could block the storage accept loop

**Id:** CLIN-002

**Severity:** high

**Title:** Idle TLS peer could block the storage accept loop

**Status:** `fixed_in_source`

#### Evidence

- `lx_administration/storage/data_plane.py:924`
- `tests/storage_manager/test_storage_data_plane.py`

**Impact:** A reachable peer could stall new storage connections before authentication.

**Fix:** Defer TLS handshake until a bounded request worker has applied the socket timeout. Close failed handshakes and release admission capacity.

**Verification:** Real TLS idle-peer and failed-handshake regressions; storage suite passed.

**Residual:** Connection floods can still consume bounded capacity. Deployment and representative load testing remain required; no throughput claim is made.

### Invalid fact responses and undisclosed observation age mislead operators

**Id:** CLIN-003

**Severity:** medium

**Title:** Invalid fact responses and undisclosed observation age mislead operators

**Status:** `fixed_in_source`

#### Evidence

- `scripts/refresh-ansible-facts.sh:147`
- `scripts/generate-cmdb-report.py`
- `tests/test_autoconf_operations.py`

**Fix:** Require exactly one valid successful nonempty setup response before replacing facts. Reject malformed flags and report field types. Display host-reported observation time, age at generation, unknown time and clock skew, together with report generation time and static-report limitations.

**Residual:** Retained facts are not a live availability check. Host-provided timestamps are not independent trusted time. Missing hosts remain absent and no clinical maximum age is inferred.

### CI could report zero dependency findings without parsing a result

**Id:** CLIN-004

**Severity:** high

**Title:** CI could report zero dependency findings without parsing a result

**Status:** `fixed_in_source`

#### Evidence

- `scripts/nix-quality.py:192`
- `tests/test_nix_quality_policy.py`
- `.github/workflows/nix-quality.yml`

**Fix:** Force the flake-checker text format in CI; require a recognized unambiguous summary. Missing or invalid results remain unknown and fail the gate. Run full flake evaluation and locked Python/tracker contracts on pull requests; retain JUnit results on failure and bound job duration.

**Residual:** Repository branch protection and successful hosted workflow runs are unverified.

**Reference:** `https://github.com/DeterminateSystems/flake-checker/blob/main/src/summary.rs`

### Clinical parser and publication contracts lack release-bound evidence

**Id:** CLIN-005

**Severity:** high

**Title:** Clinical parser and publication contracts lack release-bound evidence

**Status:** `release_blocker`

#### Evidence

- `feature-tracking/ReportReaderIntegration.yml`
- `feature-tracking/FrameCleanerIntegration.yml`

**Ownership:** lx-anonymizer and endoreg-db applications, with LuxNix deployment integration.

**Required evidence:** Test the exact packaged capability profile against representative synthetic PDF, image and video fixtures and malformed inputs. Verify clinical identity association, typed contracts, partial/cancelled attempts, retries, concurrent publication, and fail-closed anonymization. Record package identities and clinical assessor approval; source existence is insufficient to claim that these integrations work as advertised.

### Runtime dependency closure is not fully immutable

**Id:** CLIN-006

**Severity:** high

**Title:** Runtime dependency closure is not fully immutable

**Status:** `release_blocker`

#### Evidence

- `modules/nixos/services/lx-annotate-local/options/runtime.nix:286`
- `modules/nixos/services/lx-annotate-local/options/runtime.nix:323`
- `modules/nixos/services/lx-annotate-local/config.nix:374`
- `modules/nixos/services/lx-annotate-local/scripts/wheel-downgrade-guard.py`

**Observation:** The top-level 1.2.3 wheel is hash-pinned, but wheelhousePath defaults null. Dependency resolution may use the network during runtime preparation; the version guard is not a complete hashed dependency lock.

**Required evidence:** Provision and verify an immutable compatible dependency closure, then prove offline startup and rollback. Do not enable an unprovisioned wheelhouse or replace pins with unreviewed latest versions.

### Dependency age and support need release review

**Id:** CLIN-007

**Severity:** high

**Title:** Dependency age and support need release review

**Status:** `release_blocker`

#### Evidence

- `flake.lock`
- `nix-quality.yml:114`

#### Observed age days

**Nixpkgs:** 227

**`nixpkgs-unstable`:** 66

**Interpretation:** The existing two-issue ceiling permits these warnings. Passing that ceiling is not evidence of current security patches. Review supported release inputs, update deliberately, evaluate/build every affected host, and validate integration compatibility and rollback before activation.

### Downtime and HLS readiness are not proven by current acceptance

**Id:** CLIN-008

**Severity:** high

**Title:** Downtime and HLS readiness are not proven by current acceptance

**Status:** `release_blocker`

#### Evidence

- `modules/nixos/services/lx-annotate-local/subservices/lx-annotate-acceptance.nix:39`
- `docs/guides/lx-annotate-monitoring.md`
- `feature-tracking/lx_annotate_hls_operational_readiness.yml`
- `feature-tracking/lx_annotate_operational_monitoring.yml`
- `docs/lx-annotate-cluster-readiness.md`

**Observation:** The active acceptance unit checks Django, encrypted storage, worker activity and an HTTPS manifest fetch, but omits HLS readiness. The fetch lacks explicit curl deadlines and discards manifest contents. Monitoring rollout and alerts remain unverified; Kubernetes TCP readiness does not establish database, broker or shared-storage availability.

**Required evidence:** Prove release-matched probes, data freshness indicators, bounded timeout behavior and explicit unavailable/degraded/stale states. Inject dependency failures only on an isolated test deployment and measure detection and recovery; do not substitute zero latency/success for missing telemetry.

### A changed deployed MCP provider inherited previous verification

**Id:** CLIN-009

**Severity:** high

**Title:** A changed deployed MCP provider inherited previous verification

**Status:** `fixed_in_source`

#### Evidence

- `wg-lux-mcp/src/wg_lux_mcp/tools/features.py:422`
- `wg-lux-mcp/tests/test_features.py`
- `wg-lux-mcp/tests/test_server.py`

**Fix:** Effective verified status requires an immutable package identity and an exact deployed-subject match. Changed or missing provenance yields not_assessed while preserving recorded historical status and evidence. Requirement detail and compact status agree and expose invalidation.

**Verification:** 20 independent MCP tests passed in an isolated locked environment.

**Residual:** This does not age-expire assessments for an unchanged package.


## Acceptance requirements still needed

**Deployment scope:** No priority deployment selected during this review.

**Clinical maximum data age:** Not supplied; requires the clinical owner.

**Outage detection deadline:** Not supplied; requires the service owner.

**Reporting latency slo:** Not supplied; benchmark representative load before claiming speed.

**Recent data policy:** Prefer the newest authenticated, schema-valid, complete version with reviewable source identity, observation time and retrieval time. Future timestamps, unavailable sources and failed refreshes cannot establish freshness. Preserve history and expose stale or unavailable states.

**Clinical correctness:** Source and infrastructure tests cannot validate diagnostic interpretation, patient association or clinical suitability without representative fixtures, exact deployed versions and an identified domain assessor.

## Verification

### Completed

#### Entry 1

##### Command

```bash
uv run --locked pytest -q tests/test_nix_quality_policy.py tests/test_autoconf_operations.py tests/storage_manager
```

**Result:** 94 passed in 7.53s

#### Entry 2

##### Command

```bash
uv run --locked ruff check scripts/nix-quality.py tests/test_nix_quality_policy.py scripts/generate-cmdb-report.py tests/test_autoconf_operations.py lx_administration/storage/data_plane.py tests/storage_manager/test_storage_data_plane.py
```

**Result:** All checks passed.

#### Entry 3

##### Command

```bash
uv run --locked python scripts/nix-quality.py --json
```

**Result:** 319 Nix files parsed; zero lint/format findings; two retained dependency-age findings.


### Pending

- Complete repository Python suite and full flake evaluation.
- Resolve concurrent media configuration lock and verify remediation.

### Not performed

- Clinical source-data processing or assessment.
- Production fault injection, activation, migration or secret mutation.
- Fleet-wide builds, runtime acceptance, sustained load and downtime measurements.
