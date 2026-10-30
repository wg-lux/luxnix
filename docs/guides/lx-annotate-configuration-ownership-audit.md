# LX-Annotate configuration ownership investigation

This record preserves the findings and verification reported for the source
revisions and dates below. Conversion to Markdown does not revalidate runtime
state or resolve recorded blockers.

**Schema version:** 1

**Date:** 2026-10-05

**Assessed by:** codex-nix-quality-20261005

## Scope

**Kind:** Local source and scoped module evaluation, with separately attributed runtime evidence received through tracker messages

### Changed files

- `docs/guides/lx-annotate-configuration-ownership-audit.md`

**Configuration changes:** `false`

**Deployment performed:** `false`

### Limitations

- The current working tree includes unrelated staged and unstaged changes.
- No full flake check, system build, secret inspection, or live-host startup test was performed for this investigation.
- Runtime diagnostics below are reported by codex-gc02-import-diagnostics-20261005; this agent did not repeat live-host checks or verify individual job records.

## Reported symptom

**Claim:** Duplicated attrname luxnix in lx-annotate-local/config.nix may indicate central configuration is being redefined.

**Current tree result:** Not reproduced: Nix parsing and Statix both exit 0.

**Explanation:** services.luxnix and top-level luxnix are distinct option namespaces. Definitions of the same option across NixOS modules are merged by priority; a duplicate attribute within one Nix expression is a separate parse error.

### Locations

- `modules/nixos/services/lx-annotate-local/config.nix:2356`
- `modules/nixos/services/lx-annotate-local/config.nix:2551`

**Conclusion:** The namespace spelling alone does not establish an ownership bug. Scoped evaluations independently establish the issues below.

## Findings

### local-database-classified-as-external

**Id:** local-database-classified-as-external

**Priority:** high

**Status:** Confirmed dependency selection in the evaluated gs-02 configuration; database management intent and live impact require verification

**Problem:** externalPostgresConfigured infers database management from a non-null externalServices.postgresHost. Endpoint locality does not establish ownership: loopback can be externally managed.

#### Evidence

- gs-02 selects 127.0.0.1:5432, enables local PostgreSQL, and defines postgres-endoreg-setup.
- Its runtime environment and migration units omit postgres-endoreg-setup.service and postgresql.service from their after lists.
- The local dependency lists are also consumed by the web, preflight, master-key, and streamable-migration units.
- Fresh gc-02 evaluation preserves localhost:5432/endoregDbLocal and web ordering after postgresql.service and postgres-endoreg-setup.service; the gs-02 dependency-selection finding must not be attributed to gc-02.

#### Sources

- `modules/nixos/services/lx-annotate-local/config.nix:533`
- `modules/nixos/services/lx-annotate-local/config.nix:1379`
- `modules/nixos/services/lx-annotate-local/subservices/lx-annotate-runtime-env.nix:16`
- `ansible/inventory/host_vars/gs-02.yml:54`

**Impact:** If gs-02 expects LuxNix-managed PostgreSQL and credentials, the omitted dependencies create a boot-time ordering risk. An externally managed loopback database may legitimately omit them. Neither this evaluation nor the gc-02 diagnostics establishes a gs-02 database outage.

**Recommendation:** Declare database management explicitly, independently of address. Test locally managed PostgreSQL, externally managed loopback, and remote endpoints separately; derive provisioning, credential handling, and service dependencies from ownership without forcing all loopback connections into local management.

### hostname-default-conflicts-with-profile

**Id:** hostname-default-conflicts-with-profile

**Priority:** high

**Status:** confirmed by failing scoped evaluation

**Problem:** The service writes hub.enable with mkDefault based on the gs-02 hostname while the central-hub profile writes mkDefault true.

#### Evidence

- Enabling profiles.endoregCentralHub on a renamed gc-10 configuration fails with conflicting hub.enable values: profile true, service false.
- options/hub.nix separately repeats the gs-02 hostname rule as the option default.
- Current gs-02 and s-04 inventory explicitly set hub.enable, masking this conflict for those hosts.

#### Sources

- `modules/nixos/services/lx-annotate-local/config.nix:2359`
- `modules/nixos/services/lx-annotate-local/options/hub.nix:23`
- `modules/nixos/profiles/endoreg-central-hub/default.nix:48`
- `ansible/inventory/group_vars/endoreg_central_hub.yml:21`

**Impact:** A reusable profile fails when applied to another hostname without an additional explicit hub setting.

**Recommendation:** Keep machine selection in canonical inventory and profile defaults. Remove the service-level hostname mkDefault; use a neutral service option default while retaining explicit hub declarations for existing hosts.

### multiple-database-endpoint-authorities

**Id:** multiple-database-endpoint-authorities

**Priority:** medium

**Status:** confirmed; precedence is intentional in existing clustered tests

**Problem:** roles.endoreg-client.database flows into the service, but runtime.externalServices.postgresHost and postgresPort independently override service database fields with mkForce.

#### Evidence

- A scoped override sets the role host to role-db.audit.invalid and the external endpoint to external-db.audit.invalid:6543; the effective service endpoint becomes the external one.
- The role still reports its other endpoint. No consistency error is raised.
- The existing clusteredShared test expects the external endpoint to win, so removing this override without migration would change supported behavior.

#### Sources

- `modules/nixos/roles/endoreg-client/lx-annotate.nix:990`
- `modules/nixos/services/lx-annotate-local/config.nix:2418`
- `modules/nixos/services/lx-annotate-local/scripts/env.nix:116`
- `tests/lx-annotate/test_lx_annotate_nix_eval_contract.py:2150`

**Impact:** Operators can edit the central role endpoint while the running application continues using a different endpoint.

**Recommendation:** Choose one canonical connection endpoint and document its owner. Retain compatibility aliases with explicit conflict detection during migration instead of silently resolving inconsistent input with mkForce.

### local-postgres-enabled-despite-external-default

**Id:** local-postgres-enabled-despite-external-default

**Priority:** medium

**Status:** confirmed in gs-01 and s-04 configurations

**Problem:** The service tries to disable local PostgreSQL with mkDefault false when an external endpoint exists, but fleet inventory explicitly sets generic-settings.postgres.enable true.

#### Evidence

- The scoped external-endpoint probe retains services.postgresql.enable = true.
- gs-01 and s-04 use the remote PostgreSQL endpoint and still enable local PostgreSQL and postgres-endoreg-setup.
- An explicit inventory value has higher priority than the service mkDefault; this is normal module merging.

#### Sources

- `ansible/inventory/group_vars/all/30-nix.yml:120`
- `modules/nixos/services/lx-annotate-local/config.nix:2551`
- `modules/nixos/luxnix/generic-settings/default.nix:346`
- `modules/nixos/roles/postgres-default/default.nix:250`

**Impact:** The service preference and fleet policy disagree. Local database provisioning continues even when this application uses a remote database; other local consumers may still require it.

**Recommendation:** Audit all PostgreSQL consumers before changing the fleet default. Keep machine-wide PostgreSQL enablement in inventory/profiles and application-specific local database ownership in one declared contract.

### direct-service-and-provisioned-database-diverge

**Id:** direct-service-and-provisioned-database-diverge

**Priority:** medium

**Status:** confirmed by scoped direct-service evaluation; defaults are documented

**Problem:** Direct service defaults select lxAnnotateLocal on port 5433, while the automatically enabled PostgreSQL role provisions endoregDbLocal using its independent defaults.

#### Evidence

- With roles.endoreg-client disabled and the service explicitly enabled, database name/user are lxAnnotateLocal and port is 5433.
- The local PostgreSQL role remains enabled and defaultDbName remains endoregDbLocal.
- The central-hub profile also defaults application name/user to endoregDbCentral without changing roles.postgres.default.defaultDbName.
- docs/database-ownership.md documents the direct-service default difference but does not make automatic local provisioning consistent.
- The 5433/lxAnnotateLocal result belongs to the hypothetical direct-service probe. Current gc-02 evaluates to localhost:5432/endoregDbLocal, matching reported runtime metadata; do not change that working contract.

#### Sources

- `modules/nixos/services/lx-annotate-local/options/database.nix:12`
- `modules/nixos/roles/endoreg-client/database.nix:17`
- `modules/nixos/roles/postgres-default/default.nix:228`
- `modules/nixos/roles/postgres-default/default.nix:313`
- `modules/nixos/profiles/endoreg-central-hub/default.nix:38`
- `docs/database-ownership.md`

**Impact:** Direct activation does not establish a matching local application database contract; local central-hub provisioning also needs explicit alignment.

**Recommendation:** For locally managed deployments, derive provisioned database name, user, port, and credential ownership from the canonical application database contract, or reject unsupported combinations with clear assertions.


## Healthy patterns

- Service-owned options may legitimately have defaults and derived mkDefault assignments; moving all defaults into inventory would remove reusable behavior.
- Vault secret-path defaults derive from the configured Vault client options; this inspection does not establish duplicate secret ownership.
- File mover paths derive from the protected runtime root and use mkDefault, allowing deliberate host overrides.
- Matching baseline gc-10 role and service database values show that the normal EndoReg client path is coherent.

## Recommended sequence

- Add scoped regression coverage for managed local, externally managed loopback, remote database, renamed hub, direct-service provisioning, and gc-02 enabled/disabled LLM gating.
- Remove hostname policy from the reusable service while preserving explicit canonical YAML hub assignments.
- Define one database ownership contract and migrate endpoint aliases without changing current host targets.
- Preserve gc-02 database and LLM contracts and distinguish import completion from queue drainage; retain storage limits and application runtime fallback.
- Align local provisioning with that contract; audit other PostgreSQL consumers before removing fleet-wide enablement.
- Regenerate only intended host outputs through Autoconf; run quality gates and targeted host evaluation before operator-controlled deployment.

## Verification

### Commands

#### Entry 1

##### Command

```bash
devenv tasks run docs:check
```

**Exit code:** 0

#### Entry 2

##### Command

```bash
./feature-tracking/tracker.py validate
```

**Exit code:** 0

**Result:** Eleven feature definitions valid.

#### Entry 3

##### Command

```bash
./feature-tracking/tracker.py check luxnix_module_ownership_cleanup
```

**Exit code:** 1

**Result:** Existing readiness state remains 4/7; no assessments changed.

#### Entry 4

##### Command

```bash
nix-instantiate --parse modules/nixos/services/lx-annotate-local/config.nix
```

**Exit code:** 0

#### Entry 5

##### Command

```bash
statix check modules/nixos/services/lx-annotate-local/config.nix
```

**Exit code:** 0

#### Entry 6

##### Command

```bash
nix eval --impure --json --file /tmp/luxnix-ownership-audit-20261005.nix
```

**Exit code:** 0

#### Entry 7

##### Command

```bash
nix eval --impure --json --file /tmp/luxnix-ownership-hub-conflict-20261005.nix
```

**Exit code:** 1

**Expected failure:** Conflicting hub.enable values true and false.

#### Entry 8

##### Command

```bash
nix eval --impure --json --file /tmp/luxnix-ownership-hosts-20261005.nix
```

**Exit code:** 0


**Reproduction:** Extract a probe expression below to a file outside the repository and run nix eval --impure --json --file `<probe-file>`. These expressions only evaluate options; they do not activate systems or read secret contents.

### Probes

#### Ownership

##### Expression

```nix
let
  flake = builtins.getFlake "git+file:///home/admin/luxnix";
  base = flake.nixosConfigurations.gc-10;
  inspect = system: let c = system.config; s = c.services.luxnix.lxAnnotateLocal; in {
    roleDatabase = { inherit (c.roles.endoreg-client.database) host port name user; };
    serviceDatabase = { inherit (s.database) host port name user; };
    externalDatabaseDeclared = s.runtime.externalServices.postgresHost != null;
    localPostgresEnabled = c.services.postgresql.enable;
    postgresRoleDatabaseName = c.roles.postgres.default.defaultDbName;
    hubEnabled = s.hub.enable;
    deploymentRole = s.runtime.deploymentRole;
  };
  external = base.extendModules { modules = [ ({lib,...}: {
    roles.endoreg-client.database.host = lib.mkForce "role-db.audit.invalid";
    services.luxnix.lxAnnotateLocal.runtime.externalServices = {
      postgresHost = lib.mkForce "external-db.audit.invalid";
      postgresPort = lib.mkForce 6543;
    };
  }) ]; };
  direct = base.extendModules { modules = [ ({lib,...}: {
    roles.endoreg-client.enable = lib.mkForce false;
    services.luxnix.lxAnnotateLocal.enable = lib.mkForce true;
  }) ]; };
  renamedHub = base.extendModules { modules = [ ({lib,...}: {
    networking.hostName = lib.mkForce "ownership-audit-hub";
    profiles.endoregCentralHub.enable = true;
  }) ]; };
in {
  baseline = inspect base;
  externalEndpointOverride = inspect external;
  directServiceDefaults = inspect direct;
  centralProfileHubValueCanEvaluate = (builtins.tryEval renamedHub.config.services.luxnix.lxAnnotateLocal.hub.enable).success;
}
```

##### Result

```yaml
baseline:
  deploymentRole: site_node
  externalDatabaseDeclared: false
  hubEnabled: false
  localPostgresEnabled: true
  postgresRoleDatabaseName: endoregDbLocal
  roleDatabase:
    host: localhost
    name: endoregDbLocal
    port: 5432
    user: endoregDbLocal
  serviceDatabase:
    host: localhost
    name: endoregDbLocal
    port: 5432
    user: endoregDbLocal
centralProfileHubValueCanEvaluate: false
directServiceDefaults:
  deploymentRole: site_node
  externalDatabaseDeclared: false
  hubEnabled: false
  localPostgresEnabled: true
  postgresRoleDatabaseName: endoregDbLocal
  roleDatabase:
    host: localhost
    name: endoregDbLocal
    port: 5432
    user: endoregDbLocal
  serviceDatabase:
    host: lx-annotate.local
    name: lxAnnotateLocal
    port: 5433
    user: lxAnnotateLocal
externalEndpointOverride:
  deploymentRole: site_node
  externalDatabaseDeclared: true
  hubEnabled: false
  localPostgresEnabled: true
  postgresRoleDatabaseName: endoregDbLocal
  roleDatabase:
    host: role-db.audit.invalid
    name: endoregDbLocal
    port: 5432
    user: endoregDbLocal
  serviceDatabase:
    host: external-db.audit.invalid
    name: endoregDbLocal
    port: 6543
    user: endoregDbLocal
```

#### Current hosts

##### Expression

```nix
let
  flake = builtins.getFlake "git+file:///home/admin/luxnix";
  inspect = host: let
    c = flake.nixosConfigurations.${host}.config;
    s = c.services.luxnix.lxAnnotateLocal;
  in {
    inherit host;
    serviceEnabled = s.enable;
    externalDatabaseHost = s.runtime.externalServices.postgresHost;
    database = { inherit (s.database) host port name user; };
    localPostgresEnabled = c.services.postgresql.enable;
    localProvisionedDatabase = c.roles.postgres.default.defaultDbName;
    postgresSetupExists = builtins.hasAttr "postgres-endoreg-setup" c.systemd.services;
    runtimeEnvAfter = c.systemd.services.lx-annotate-runtime-env.after;
    migrateAfter = c.systemd.services.lx-annotate-migrate.after;
    webAfter = c.systemd.services.lx-annotate.after;
  };
in map inspect [ "gc-02" "gs-02" "s-04" "gs-01" ]
```

##### Result

```yaml
- database:
    host: localhost
    name: endoregDbLocal
    port: 5432
    user: endoregDbLocal
  externalDatabaseHost: null
  host: gc-02
  localPostgresEnabled: true
  localProvisionedDatabase: endoregDbLocal
  migrateAfter:
  - network.target
  - lx-annotate-runtime-env.service
  - systemd-tmpfiles-setup.service
  - lx-annotate-wheel-runtime.service
  - redis-lx-annotate.service
  - postgresql.service
  - postgres-endoreg-setup.service
  - managed-secrets-setup.service
  postgresSetupExists: true
  runtimeEnvAfter:
  - systemd-tmpfiles-setup.service
  - managed-secrets-setup.service
  - postgres-endoreg-setup.service
  serviceEnabled: true
  webAfter:
  - network.target
  - lx-annotate-request-throttle.socket
  - lx-annotate-request-throttle.service
  - lx-annotate-runtime-env.service
  - lx-annotate-load-base-data.service
  - lx-annotate-master-key-check.service
  - endoreg-django-setup.service
  - systemd-tmpfiles-setup.service
  - redis-lx-annotate.service
  - postgresql.service
  - postgres-endoreg-setup.service
  - managed-secrets-setup.service
- database:
    host: 127.0.0.1
    name: endoregDbLocal
    port: 5432
    user: endoregDbLocal
  externalDatabaseHost: 127.0.0.1
  host: gs-02
  localPostgresEnabled: true
  localProvisionedDatabase: endoregDbLocal
  migrateAfter:
  - network.target
  - lx-annotate-runtime-env.service
  - systemd-tmpfiles-setup.service
  - lx-annotate-wheel-runtime.service
  - redis-lx-annotate.service
  - managed-secrets-setup.service
  postgresSetupExists: true
  runtimeEnvAfter:
  - systemd-tmpfiles-setup.service
  - managed-secrets-setup.service
  serviceEnabled: true
  webAfter:
  - network.target
  - lx-annotate-request-throttle.socket
  - lx-annotate-request-throttle.service
  - lx-annotate-runtime-env.service
  - lx-annotate-load-base-data.service
  - lx-annotate-master-key-check.service
  - endoreg-django-setup.service
  - systemd-tmpfiles-setup.service
  - redis-lx-annotate.service
  - managed-secrets-setup.service
- database:
    host: 172.16.255.22
    name: endoregDbCentral
    port: 5432
    user: endoregDbCentral
  externalDatabaseHost: 172.16.255.22
  host: s-04
  localPostgresEnabled: true
  localProvisionedDatabase: endoregDbLocal
  migrateAfter:
  - network.target
  - lx-annotate-runtime-env.service
  - systemd-tmpfiles-setup.service
  - lx-annotate-wheel-runtime.service
  - managed-secrets-setup.service
  postgresSetupExists: true
  runtimeEnvAfter:
  - systemd-tmpfiles-setup.service
  - managed-secrets-setup.service
  serviceEnabled: true
  webAfter:
  - network.target
  - lx-annotate-request-throttle.socket
  - lx-annotate-request-throttle.service
  - lx-annotate-runtime-env.service
  - lx-annotate-load-base-data.service
  - lx-annotate-master-key-check.service
  - endoreg-django-setup.service
  - systemd-tmpfiles-setup.service
  - managed-secrets-setup.service
- database:
    host: 172.16.255.22
    name: endoregDbLocal
    port: 5432
    user: endoregDbLocal
  externalDatabaseHost: 172.16.255.22
  host: gs-01
  localPostgresEnabled: true
  localProvisionedDatabase: endoregDbLocal
  migrateAfter:
  - network.target
  - lx-annotate-runtime-env.service
  - systemd-tmpfiles-setup.service
  - lx-annotate-wheel-runtime.service
  - managed-secrets-setup.service
  postgresSetupExists: true
  runtimeEnvAfter:
  - systemd-tmpfiles-setup.service
  - managed-secrets-setup.service
  serviceEnabled: true
  webAfter:
  - network.target
  - lx-annotate-request-throttle.socket
  - lx-annotate-request-throttle.service
  - lx-annotate-runtime-env.service
  - lx-annotate-load-base-data.service
  - lx-annotate-master-key-check.service
  - endoreg-django-setup.service
  - systemd-tmpfiles-setup.service
  - managed-secrets-setup.service
```

#### Hub conflict

##### Expression

```nix
let
  flake = builtins.getFlake "git+file:///home/admin/luxnix";
  renamedHub = flake.nixosConfigurations.gc-10.extendModules {
    modules = [ ({ lib, ... }: {
      networking.hostName = lib.mkForce "ownership-audit-hub";
      profiles.endoregCentralHub.enable = true;
    }) ];
  };
in renamedHub.config.services.luxnix.lxAnnotateLocal.hub.enable
```

**Expected exit code:** 1

#### Gc02 llm gating

##### Expression

```nix
let
  flake = builtins.getFlake "git+file:///home/admin/luxnix";
  base = flake.nixosConfigurations.gc-02;
  disabled = base.extendModules { modules = [ ({ lib, ... }: {
    services.luxnix.lxAnnotateLocal.runtime.llm.enable = lib.mkForce false;
  }) ]; };
  inspect = system: let
    c = system.config;
    runtime = c.services.luxnix.lxAnnotateLocal.runtime;
    worker = c.systemd.services.lx-annotate-celery-llm-inference-worker;
  in {
    enabled = runtime.llm.enable;
    mode = runtime.llmInferenceWorker.mode;
    flag = c.systemd.services.lx-annotate.environment.LLM_ENABLED;
    wantedBy = worker.wantedBy;
    requiresOllama = builtins.elem "ollama.service" worker.requires;
    afterOllama = builtins.elem "ollama.service" worker.after;
  };
in { enabled = inspect base; disabled = inspect disabled; }
```

##### Result

```yaml
disabled:
  afterOllama: false
  enabled: false
  flag: 'false'
  mode: manual
  requiresOllama: false
  wantedBy: []
enabled:
  afterOllama: true
  enabled: true
  flag: 'true'
  mode: always
  requiresOllama: true
  wantedBy:
  - multi-user.target
```

### Alignment recheck

**Date:** 2026-10-05

**Boundary:** Fresh scoped evaluations of the shared tree after the worker helper extraction; results describe this evaluated tree, not a subsequent concurrent mitigation or the deployed fleet.

#### Source sha256

**`modules/nixos/services/lx-annotate-local/config.nix`:** 924ca25cff4c4b08b0267522cb7f1ffa7f9d48254d82bdd9a78b19435be72982

**`modules/nixos/services/lx-annotate-local/worker.nix`:** 75aa5b3769498e018889b7fedc7d552ddc13d6a6567ff73f5d659b75ad388a5e

**`modules/nixos/services/lx-annotate-local/options/runtime.nix`:** a45b1495fa76e41af051a145e7883764fb9e61c6b1eb869a51ff928c36cb2e98

**`ansible/inventory/host_vars/gc-02.yml`:** d7120d0d7d18177ef90292462b97661fc7526de36f34193ce522d13186173f50

**`systems/x86_64-linux/gc-02/default.nix`:** acec644feed87ab223b5877f1cd06ab5f4706d4763f950d479403d9eccaacffc

#### Commands

##### Entry 1

```yaml
command: nix-instantiate --parse modules/nixos/services/lx-annotate-local/config.nix
exit_code: 0
```

##### Entry 2

```yaml
command: statix check modules/nixos/services/lx-annotate-local/config.nix
exit_code: 0
```

##### Entry 3

```yaml
command: nix eval --impure --json --file /tmp/luxnix-alignment-ownership-20261005.nix
exit_code: 0
```

##### Entry 4

```yaml
command: nix eval --impure --json --file /tmp/luxnix-alignment-current_hosts-20261005.nix
exit_code: 0
```

##### Entry 5

```yaml
command: nix eval --impure --json --file /tmp/luxnix-alignment-hub_conflict-20261005.nix
exit_code: 1
```

##### Entry 6

```yaml
command: nix eval --impure --json --file /tmp/luxnix-alignment-gc02-llm-20261005.nix
exit_code: 0
```


#### Verified contracts

- gc-02 database remains localhost:5432/endoregDbLocal with PostgreSQL and credential setup in web After.
- LLM enabled: mode always, LLM_ENABLED true, multi-user.target, Requires/After ollama.service.
- LLM disabled: mode manual, LLM_ENABLED false, WantedBy empty, no Ollama Requires/After.
- gs-02 evaluated loopback endpoint omits local PostgreSQL ordering; management intent still requires an explicit contract.
- Renamed-hub evaluation still fails on conflicting hub.enable defaults.

## Review alignment

### Messages reviewed

#### 3c3c3ea3f4f74298b33f8a500734417e

**Id:** 3c3c3ea3f4f74298b33f8a500734417e

**Sender:** codex-gc02-import-diagnostics-20261005

**Subject:** gc-02 runtime evidence to guide ownership mitigation

##### Applied to

```yaml
- Database management versus endpoint locality
- Separation of gc-02 import failures from gs-02 ordering risk
- Runtime evidence attribution and job-completion limits
- Preservation of LLM gating, storage controls, endpoint precedence, and existing gc-02 database contract
```

#### 6b09764632db4f989fc855b30378b722

**Id:** 6b09764632db4f989fc855b30378b722

**Sender:** codex-gc02-import-diagnostics-20261005

**Subject:** Taking implementation ownership per user request

##### Applied to

```yaml
- Implementation handoff and separation of report work from configuration changes
```


### Implementation handoff

**Owner:** codex-gc02-import-diagnostics-20261005

**Assignment source:** Tracker message 6b09764632db4f989fc855b30378b722 reports explicit user assignment.

#### Reported scope

- Explicit database ownership
- Endpoint compatibility and consistency checks
- Removal of service hostname hub policy
- Validation of local provisioning contracts

**Report boundary:** This agent owns report alignment only. No mitigation is marked resolved by the assignment message; implementation evidence will be recorded separately by the implementing agent.

**Review request:** Send exact changed files, scoped test results, and any unresolved migration or provisioning blockers before interpreting original findings as resolved.

### Gc02 runtime evidence

**Provenance:** Reported live observations in message 3c3c3ea3f4f74298b33f8a500734417e, dated 2026-10-05; not independently repeated by this report agent.

#### Earlier report consumer

**Llm worker:** inactive/dead; WantedBy empty

**Llm inference queued tasks:** 6

**Task name:** `endoreg_db.report_llm_import`

**Other inspected queues:** empty

**Filewatcher submitted:** 0

**Retry due upload jobs due count:** 0

**Interpretation:** Missing report consumer was established; a database outage was not established.

#### Database

**Endpoint:** localhost:5432

**Database:** endoregDbLocal

**User:** endoregDbLocal

**Port 5433:** absent

**Limitations:** Admin SQL rejected by pg_hba; service password unreadable. Individual job states were not verified.

#### Video failures

**Date:** 2026-10-02

**Source log interval utc:** 11:41 through 13:00 UTC

**Failed video reimport executions:** 6

**Failure:** encrypt_stream -> destination.write(ciphertext): OSError errno 28 (ENOSPC)

**Reported free space at diagnosis:** Approximately 5 GiB

**Retry behavior:** Installed task retries MediaOperationDeferred, not ordinary ENOSPC; newly freed space does not automatically resume these failed jobs.

##### Existing capacity controls

```yaml
watcher_below_5_gib: warning only
video_warn_gib: 2
video_stop_projected_free_gib: 1
environment_overrides: None reported
```

**Mitigation constraint:** Preserve storage controls while repairing the report consumer; do not conflate ENOSPC recovery with LLM queue consumption.

#### Later handoff

**Web:** active

**Llm worker:** active; WantedBy multi-user.target; Requires/After ollama.service

**Llm inference queue length:** 0

##### Web database ordering

```yaml
- postgresql.service
- postgres-endoreg-setup.service
```

**Activation attribution:** The diagnosing agent reported no activation. A change to running state was observed; actor and revision were not established.

**Completion limit:** An empty queue and an active worker do not prove successful report completion or recovery of the failed video jobs.

#### Reported prior verification

- autoconf:check and docs:check exited 0 before subsequent concurrent edits.
- Isolated Autoconf run_pipeline exited 0; only reviewed generated gc-02 output was published.
- Enabled/disabled LLM gating probes and gc-02 system toplevel derivation evaluation exited 0.
- A cache HTTP 401 occurred; other caches succeeded. This does not contradict the separate incomplete full-flake attempt recorded in nix-quality.yml.

### Preservation constraints

- Preserve gc-02 localhost:5432/endoregDbLocal and existing PostgreSQL/credential ordering.
- Preserve runtime.llm.enable -> LLM_ENABLED and conditional worker autostart; retain local Ollama Requires/After ordering.
- As reported for lx-anonymizer report_reader.py and frame_cleaner.py, honor LLM_ENABLED before runtime provider/model checks and retain existing non-LLM fallback. This report agent has not independently inspected those application files.
- Do not gate the queue consumer on a one-time provider-health probe.
- Preserve external/clustered endpoint precedence through an explicit compatibility migration and conflict checks.
- Audit other PostgreSQL consumers before changing fleet-wide enablement.
- Fix generated gc-02 Statix parentheses through renderer-supported canonical input and regeneration, not a direct generated-file edit.

### Required mitigation cases

- Locally managed database with credential and service ordering
- Externally managed loopback database without automatic local provisioning
- Remote database with compatible endpoint precedence
- Renamed host using the reusable central-hub profile
- Direct-service defaults and matching local provisioning
- gc-02 LLM enabled and disabled after worker refactoring
