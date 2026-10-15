# LX Terminology package hosting and publication

**Schema version:** 1

**Owner:** LuxNix maintainers

**Canonical topic:** LX terminology package hosting and publication

**Purpose:** Upload versioned ZIP bundles once and download them publicly during application runs.

## Deployment

**Host:** s-02

**Domain:** `terminology.endo-reg.net`

**Public URL:** `https://terminology.endo-reg.net`

**State:** `configured_in_inventory_not_deployed`

### Prerequisites

- Point the public DNS record at the s-02 public web ingress.
- Verify the managed certificate covers terminology.endo-reg.net.
- Provision a random upload token of at least 32 ASCII characters at /run/secrets/lx-terminology-upload-token through the managed secret workflow.
- Use the documented host deployment workflow after reviewing the source revision and build.

**Token lifecycle:** LoadCredential reads the root-owned secret at service start; restart lx-terminology after rotation.

**TLS:** Reuses s-02 nginx-host certificate synchronization; no plaintext public listener.

**Persistence:** `/var/lib/lx-terminology/packages.sqlite3`

**Backup:** Use SQLite online backup or stop the service before copying the database; retain the host's encrypted backup policy.

**Readiness:** DNS, certificate coverage, secret provisioning, host build, activation and public HTTP acceptance remain operator checks.

## Contract

**Catalog:** GET /api/packages

**Publish:** POST /api/packages with raw application/zip body and Authorization bearer token

**Download:** GET /packages/{sha256}.zip

**Upload response:** name, version, sha256, size, url

**Immutable identity:** A different ZIP for an existing name/version returns 409; identical bytes return 200.

**Limits:** 64 MiB uploaded ZIP, 256 MiB expanded bytes, 4096 entries, 64 KiB root config.

**Validation:** ZIP paths, size, readability and root identity; full domain and graph validation remains with the consuming application.

**CORS:** Public reads and explicit bearer uploads; browser requests omit cookies.

**Public content:** Publish approved terminology only; every package and catalog entry is publicly readable.

**Nix boundary:** Nix packages the server software only. Bundle contents live in the writable runtime database.

## Publication

**Browser:** Open the host URL, select an editor-exported ZIP, supply the upload token, and publish.

**Editor:** The package publication panel uploads the current generated bundle and returns its public download link. The token is never persisted.

### Data models

**Source:** `/home/admin/lx-data-models/lx_dtypes/data`

**Tool:** `modules/nixos/services/lx-terminology/publish.py`

**Dependencies:** Recursively include referenced modules and depends_on entries from the same data root; missing or ambiguous dependencies fail.

**Version selection:** External dependencies resolve by config name outside versions/; ambiguous names fail. Historical root versions do not pin historical dependency versions.

#### Example

```bash
python modules/nixos/services/lx-terminology/publish.py /home/admin/lx-data-models/lx_dtypes/data/dgvs_reporting --data-root /home/admin/lx-data-models/lx_dtypes/data --server https://terminology.endo-reg.net --token-file /path/to/operator-token
```

#### Python dependencies

- flask
- pyyaml

**Behavior:** Reads source files without modifying them and produces deterministic ZIP bytes; no Nix rebuild is involved.

## Consumption

**Reporting:** Paste the returned package link in ReportingShell's public package link control.

**Runtime:** Browser downloads with a 64 MiB bound and SHA-256 verification, then calls the existing authenticated terminology import.

**Activation:** Existing draft saving, server-side validation, registration and active-terminology reconciliation remain authoritative.

**Editor import:** Download the hosted ZIP and use ZIP öffnen or ZIP zusammenführen; the editor's existing editable-layout restrictions still apply.

## Verification

**Server:** python -m pytest tests/lx-terminology/test_package_host.py -q

**Application:** npm exec vitest run src/api/__tests__/terminologyPackageHost.test.ts src/api/__tests__/terminologyApi.test.ts

**Editor:** npm test

**Local import blocker:** Full domain import against /home/admin/lx-data-models is blocked by the existing ReportTemplate.py NameError for datetime during model import. Structural export passed for all seven catalog entries; this is not evidence of clinical graph validity.
