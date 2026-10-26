# OpenBao hub backend and Vault migration

`luxnix.openbao.enable` adds an isolated OpenBao service using the locked Nixpkgs
package (currently 2.6.4). It is disabled by default. Existing Vault services,
AppRole files, application secret interfaces and storage are unchanged.

The target architecture is defined in
[OpenBao target architecture](openbao-architecture.md) and accepted against
`boot-encryption-acceptance.yml` (schema 1.3). Volumes unlock through a
host-local, TPM-sealed OpenBao; this module is the central hub instance on
gs-02 for host identities, PKI and allowlisted center salts. The central
volume-release scenario exercised by the VM test below belongs to the earlier
architecture. Its KV, cert-auth, single-use token and revocation results still
apply to hub identity provisioning, but no longer to volume unlock.

Before enabling the backend through canonical inventory, declare an encrypted
mount or bind at `/var/lib/openbao`, and supply runtime TLS certificate and key
paths. The service checks encryption and protected swap before startup, stops
when its mount disappears, and uses systemd credentials for TLS. It defaults to
loopback port 8300 with TLS and client certificates enabled; production address,
server pinning and firewall policy must be supplied deliberately. It uses a
separate single-node Raft backend. It neither initializes nor unseals itself.
The existing NixOS service avoids automatic restart during rebuilds; configuration
changes requiring restart need a controlled restart and unseal ceremony.

OpenBao [certificate authentication](https://openbao.org/docs/auth/cert/) can
verify the client certificate. The boot client must separately use a non-exportable
TPM key; a PEM key path or successful certificate login does not prove that.
Certificate login also does not establish root/Nix-store integrity, or enforce
current device revocation on every subsequent key read. Enrollment, per-volume
policies, audit operations, per-request revocation, integrity verification and deployment
integration remain required before enabling client unlock.

Server auto-unseal is a separate concern. OpenBao offers a
[PKCS#11 seal](https://openbao.org/docs/2.6.x/configuration/seal/pkcs11/), but the
selected TPM provider, key mechanism, runtime access and independent recovery
must be tested. This module does not claim TPM auto-unseal or grant hardware
access. Default Shamir unseal requires custodians after server restart.

Do not point OpenBao at the current Vault data directory. The upstream
[migration guide](https://openbao.org/docs/guides/migration/) tests a specific
Vault 1.14.1 to OpenBao 2.2.0 path, not arbitrary installed versions. Replacing
Vault remains a separate migration with backup, compatibility and recovery tests.
No host has been activated by adding this module; fleet acceptance remains open.


## Storage choice and local VM check

The locked Nixpkgs package is OpenBao **2.6.4**. Its tagged
[backend registry](https://github.com/openbao/openbao/blob/v2.6.4/command/commands.go)
registers both `file` and `raft`; `storage.file` is supported, not a configuration
error. We select [Raft](https://openbao.org/docs/2.6.x/configuration/storage/raft/)
because a single node needs no additional service and can later grow into an
ENC-08 redundant cluster. The node ID uses the hostname; cluster advertisement
and listener are restricted to loopback port 8301. Future multi-node operation
requires reviewed reachable cluster addresses, membership, quorum and recovery
tests. A single node provides no availability redundancy. Existing file-backend
data must not simply be opened as Raft data; migration is outside this change.

The persistent state guard rejects tmpfs at `/var/lib/openbao`. Only the TLS
private-key guard permits runtime tmpfs, still requiring protected swap. Neither
guard unlocks storage. The service retains the upstream sandbox and core-dump
restriction and requires the encrypted mount before startup. A declarative file
audit device writes `/var/lib/openbao/audit.jsonl` on that same mount. OpenBao
2.6.4 rejects API audit creation by default; the module uses its supported
[configuration stanza](https://openbao.org/docs/2.6.x/configuration/audit/)
instead of enabling the unsafe API switch. Audit rotation, capacity monitoring
and off-host retention still need an operational design before deployment.

Run the cataloged local check from the repository root:

```bash
devenv tasks run tests:openbao-vm
```

This builds `checks.x86_64-linux.openbao-release`, a NixOS VM using the actual
`luxnix.openbao` service on a disposable LUKS2 disk. It needs local Nix VM build
support/KVM; no physical TPM, remote host or existing Vault is used. It generates
its CA, server/client private keys, volume values, root token and 2-of-3 Shamir
shares inside the guest at runtime. Sensitive API payloads never pass through
the driver or Nix store. Credentials are in private guest tmpfs; state and audit
are on the encrypted test disk. Two logical HTTPS clients use distinct **file
certificates**, not TPM keys: **ENC-06 remains open**.

The guest checks initialization and threshold unseal, one KV v2 path per host
and volume (`volume-release/data/<host>/<volume>`), exact-path policies,
per-host Cert roles, cross-host and unknown-volume denials, single-use tokens
with at most 30 seconds TTL, expiration, accessor revocation, application-policy
403 responses, and audit identity/path with HMAC-protected values. A service
restart must preserve initialization, become sealed and return HTTP 503 with
an explicit sealed error. No recovery or local-secret fallback is implemented.

### Removing a device role safely

**Deleting a Cert role alone does not revoke previously issued tokens.** The
VM deliberately verifies this counterexample with an unused token. OpenBao
[policy contents are evaluated on each request](https://openbao.org/docs/concepts/policies/).
The tested removal sequence first replaces that host's exclusive release policy
with a deny rule for `volume-release/*`, then deletes its Cert role. The next
read using an outstanding token receives 403, and new logins fail. Keep that
deny policy in place until all earlier tokens have expired or been revoked;
reusing its name for a new grant too early could reauthorize old tokens.
Accessor revocation separately proves that an already issued token cannot read
again. A short TTL or `num_uses=1` alone is not immediate revocation.

This is backend evidence, not a deployed enrollment/removal command. ENC-05 and
ENC-15 remain incomplete until the fleet client and operator workflow enforce
this ordering and fresh authorization. ENC-07 VPN bootstrap and ENC-09 system
integrity are not exercised. ENC-20 rotation/idempotent enrollment and ENC-21/22
fleet deployment and operational commands remain open.

On gs-02, OpenBao Shamir unseal is a **second, independent custodian ceremony**
in addition to the existing application's Vault unseal. ENC-08(b), unattended
site recovery, is not promised. The VM demonstrates resealing of OpenBao only;
it does not demonstrate gs-02 recovery, hardware protection or multi-node HA.


The local run on 2026-10-26 passed `pytest tests/test_openbao.py` (2 tests) and
`devenv tasks run tests:openbao-vm` (80.72 seconds in the VM driver). The acceptance
catalog records this as VM-only evidence. Initial runs exposed a missing Raft
data directory and the version's declarative-audit requirement; both are fixed
in the module. Setup allows 60 seconds for the initial Raft election and waits
for KV v2 initialization; ordinary release requests retain a 10-second deadline.

The required `nix-quality:check`, `docs:check` and structure validation also
passed. An additional `pytest -q tests/test_devenv_command_catalog.py` run had
22 passes and two failures: the existing native `rebuild-host-switch` and
`rebuild-host-boot` entries conflict with tests requiring Devenv wrappers.
Those unrelated entries and the tests were preserved. Tracker validation passed
(11 definitions); `tracker.py check luxnix_secret_lifecycle_readiness` remains
not production-ready (0/13). These broader blockers are not waived by the VM result.

## Fleet secrets-manager review and Vault migration plan

Reviewed on 2026-10-26 against the working tree. The configured packages evaluate
to Vault **1.21.4** and OpenBao **2.6.4**; these are build inputs, not a claim about
the versions currently running on gs-02. The upstream in-place migration guide
only establishes Vault 1.14.1 to OpenBao 2.2.0 compatibility. Do not open the
production Vault 1.21.4 data directory with OpenBao, or downgrade Vault to fit
that guide. Use a separate target and a rehearsed logical migration unless a
supported, tested snapshot conversion for these exact versions is established.

### Findings and target client contract

| Priority | Finding | Required disposition |
| --- | --- | --- |
| High | `tpm_release.py` was built as a central volume-key fetcher. Under the current architecture its TPM identity and mTLS transport serve hub enrollment and center salt delivery; volume unlock uses the local OpenBao. | Move identity and transport into the shared client described in the architecture plan. Never reuse a hub identity token for local volume records or application reads. |
| High, fixed during review | The curl invocation inherited default configuration, and request path/config inputs lacked strict validation. | The current client disables curlrc, validates HTTPS URLs and path components, rejects control characters, and classifies malformed response shapes. Regression tests include a hostile curlrc and injected token directives. |
| High | `vault-auth-setup` is a one-shot login; AppRole tokens are configured for 1 hour with a 4 hour maximum. | Implement bounded reauthentication before expiry, atomic runtime publication, and consumer credential reload. Test beyond maximum TTL and through a server outage; a renewal-only timer cannot exceed maximum TTL. |
| High | The current application stack still calls `pkgs.vault` and uses `VAULT_*` runtime files across enrollment, managed secrets and hub PKI. | Add one shared client command/adapter selection and contract-test all consumers against OpenBao before changing inventory. Avoid independent copies of the existing Vault module. |
| High, fixed after review | The fetch path previously bypassed TSS2 attribute validation. | It now validates TPM-generated, fixedTPM/fixedParent, sign-only key attributes before network access; plaintext-key rejection is regression-tested. Physical enrollment and system integrity remain separate acceptance requirements. |
| High | Neither hardware identity nor a TPM-sealed local seal attests root/Nix-store integrity. | Complete ENC-09 before enabling unattended local unlock. Software TPM tests are not hardware acceptance. |
| Medium | Audit retention, capacity alarms, off-host backups and restore are not operationally established. | Prove audit-full behavior and encrypted off-host restore before the backend owns application secrets. |

The fleet client should have two explicit lifecycles: short-lived single-use
volume release before mounts, and renewable or reauthenticated application
sessions after mounts. Application consumers retain `DJANGO_SECRET_KEY_FILE`,
`DJANGO_DB_PASSWORD_FILE`, `LX_ANNOTATE_MASTER_KEY_FILE` and their existing file
permissions. Existing `/etc/secrets/vault` and `/run/luxnix/vault` names may remain
compatibility interfaces during migration. Tokens are opaque; do not validate
only Vault-specific prefixes. Endpoint, CA pin and authentication generation must
switch together, with no automatic fallback to a different secrets server.

The local encrypted admin vault (`.lxv`, implemented with Ansible Vault) is a
separate custody mechanism. Replacing the HashiCorp server does not replace that
vault or its independent recovery export.

### Ordered migration gates

1. **Inventory and baseline — secrets custodian.** Through the cataloged
   connectivity and inventory workflows, capture running versions, seal and
   storage configuration, auth/secrets mounts and plugin versions, policies,
   identity entities/groups/aliases, AppRoles, certificate roles, audit devices,
   leases and consumer endpoints. Record metadata only in evidence. Enumerate
   KV v2 versions, deletion/destruction state, custom metadata and CAS settings.
   Inventory PKI issuers, CA chains, CRLs, issuer IDs and key exportability;
   identify Transit keys, dynamic credentials and non-exportable material.
   Unknown mounts or plugins block migration.
2. **Recovery rehearsal — custodians and operator.** Take encrypted consistent
   Vault snapshots and independently stored recovery material. Restore into an
   isolated environment and demonstrate native recovery before reading any
   production secret for transfer. Back up and restore OpenBao separately.
   Confirm gs-02/VPN/storage bootstrap has no dependency on the service it
   unlocks. Keep recovery keys and backups independently accessible.
3. **Isolated target — platform maintainer.** Provision separate OpenBao state,
   TLS identity, policies and audit destinations through canonical inventory.
   Require explicit initialization and unseal custody, capacity monitoring,
   encrypted backups and alerts. Choose a documented single-node recovery SLA
   or a tested multi-node Raft quorum; a second directory on gs-02 is not HA.
   Never join OpenBao to the production Vault Raft cluster as an experiment.
4. **Client compatibility — application maintainer.** Exercise real OpenBao
   AppRole login, KV v2 reads, PKI issuance/renewal, certificate revocation,
   policy denial, token expiry and reauthentication using the actual production
   scripts. Include `roles/managed-secrets`, hub enrollment/reconciliation,
   Django, Celery workers and hub transfer. Verify pinned TLS and opaque token
   handling, missing-secret failure and offline behavior. Preserve application
   key bytes and key IDs; switching managers is not a key rotation.
5. **Transfer rehearsal — secrets custodian.** Use the cataloged
   `openbao-provision` workflow below for selected current KV v2 values;
   no ad-hoc SSH/scp or plaintext export files.
   Transfer through authenticated APIs using bounded identities and encrypted
   or non-swappable staging, with logs limited to paths, versions and outcomes.
   Fail on target conflicts. Verify values in protected memory without logging
   values or reusable hashes. Reconcile metadata as well as current values.
   Destroyed KV versions cannot be recovered; document historical retention
   limits instead of inventing placeholder versions. Recreate policies and
   identity mappings in dependency order. Do not copy live tokens, leases or
   AppRole SecretIDs as if portable; issue fresh target credentials.
6. **PKI and special engines — PKI custodian.** If issuer keys cannot be
   exported, use an explicitly approved issuer rotation with overlapping trust
   and certificate reissuance. Prove old and new CRL/expiry handling before
   removing trust. Never silently replace a CA or Transit key. Dynamic-secret
   leases must drain or be reissued against the same external systems with
   tested rollback. Unsupported engine material blocks its consumer wave.
7. **Canary and waves — fleet operator.** Keep the same group-level client
   contract and select waves through the deployment inventory. Freeze writes,
   rotation and reconcilers for the affected namespace, perform the final
   verified delta, then switch endpoint, pin and fresh credentials atomically.
   Allow only one authoritative writer per namespace. Verify cold start,
   rebuild, restart, secret refresh, token maximum TTL, application decrypt,
   DB access, PKI and hub transfer before expanding. Complete every fleet host,
   including intermittently offline hosts; no host-specific weaker profile.
8. **Retire — custodians after explicit acceptance.** Require all consumers
   accounted for, no unexplained old-server traffic over the longest relevant
   token/lease/renewal/offline interval, independent recovery drill, and retained
   rollback evidence. Revoke old credentials and remove the old endpoint only
   after acceptance. Data deletion and removal of recovery material are separate
   approved operations, never automatic consequences of switching clients.

### Rollback boundary

Before target writes, revert endpoint, pin and credential generation together
and validate the unchanged Vault source. Once OpenBao has issued credentials,
rotated a key or accepted writes, a DNS rollback alone is unsafe. Freeze target
writes, identify the authoritative delta and external credential effects,
reconcile through the rehearsed transfer path, and revoke or drain target
leases before restoring the old clients. If reconciliation is not proven,
stop expansion and repair forward; never let both backends rotate the same
application identity independently.

### Acceptance evidence still required

Migration is planned, not authorized for execution by this review. The existing
OpenBao VM lane demonstrates a disposable volume-release backend; it does not
prove production Vault migration or the actual TPM client against OpenBao.
Required new evidence includes that end-to-end combination, the application
compatibility suite, a transfer/rollback rehearsal, recovery from independent
storage and the full fleet boot criteria. Keep status in the existing secret
lifecycle tracker; this plan does not mark any release gate complete.


Review validation: `python -m pytest -q tests/test_tpm_release.py
 tests/test_openbao.py tests/test_secret_rotation_catalog.py` passed 16 tests.
The TPM tests use disposable software TPMs and a synthetic mTLS API; they do
not prove real OpenBao interoperability or hardware assurance. Documentation
checks and structure validation passed. The lifecycle readiness check remains
blocked at 0/13; none of these results authorizes fleet cutover.

The TPM client handoff resolved the previously reported formatting blocker in
`modules/nixos/luxnix/tpm-release-client/default.nix`. The client remains opt-in
and is not yet connected to automatic container unlock.

## Repeatable Vault-to-OpenBao provisioning

`devenv shell openbao-provision` reconciles explicitly selected **current KV v2
records**. It does not initialize servers, create mounts, copy authentication
state, switch consumers or migrate historical versions, PKI, Transit or dynamic
leases. Prepare target mounts, audit and scoped policies first. Source access
requires read on selected data and metadata paths; target access additionally
requires create/update on selected data paths. Use fresh target credentials.

Keep the reviewed manifest in a local `.yml` file. This schema example contains
references only; replace example origins and paths with the reviewed inventory:

```yaml
version: 1
source:
  url: https://vault.example.org:8200
  ca_file: /etc/luxnix/vault-ca.pem
  token_file: /run/luxnix-migration/vault.token
target:
  url: https://openbao.example.org:8300
  ca_file: /etc/luxnix/openbao-ca.pem
  token_file: /run/luxnix-migration/openbao.token
records:
  - id: application-key
    source_mount: kv
    source_path: applications/site/key
    target_mount: kv
    target_path: applications/site/key
    mode: immutable
    required_fields: [key]
```

Optional `client_cert_file` and `client_key_file` enable mutual TLS per endpoint.
Token and private-key files must be owner-private regular files without symlinks
on encrypted storage or protected tmpfs. Swap must be encrypted or disabled;
memory-only zram is accepted. Tokens are never command arguments. TLS verifies
the configured CA and hostname; proxies and redirects are not used. The process
disables core dumps.

Preview and apply the same reviewed wave:

```bash
devenv shell openbao-provision --config /secure/migration.yml
devenv shell openbao-provision --config /secure/migration.yml --apply
devenv shell openbao-provision --config /secure/migration.yml --record application-key --apply
```

An apply invocation authorizes that manifest's selected records without extra
interactive prompts on reruns. The command validates the entire wave before its
first write, creates missing records with CAS zero and reads back every write.
Equal values create no new version. After a lost acknowledgement, readback
checks whether the write succeeded. Rerun after a partial failure: matching
records remain unchanged and missing records are copied. No local success
marker, plaintext export or reusable value hash is written.

`immutable` protects key material by rejecting different existing values. Use
`source_authoritative` only where reviewed ownership remains with Vault: updates
use the observed target version as a compare-and-set condition. A concurrent
different target write is not overwritten. Freeze source writes for final
transfer and endpoint cutover; reconciliation is not a multi-record transaction.

When Vault is stopped, unreachable, sealed or uninitialized, provisioning checks
that every selected OpenBao record exists with its required fields, then succeeds
with `mode: target_only`. No source token is needed in that case. After retirement
set `source: null` to remove the source connection and CA dependency entirely.
Missing required target records still fail: secret material cannot be recovered
from a nonexistent source. TLS/authentication errors, malformed records and
record tombstones remain errors. A live source missing a selected record is an
error, not an invitation to generate a replacement key. Target-only validation
proves presence and shape, not equality to an unavailable original; preserve
independent recovery evidence. JSON output contains IDs, actions and versions.

Run the actual-service rehearsal with:

```bash
devenv tasks run tests:bao-migration-vm
```

It uses pinned Vault and OpenBao binaries with verified HTTPS in a disposable VM
and ephemeral tmpfs state. It covers preview, first copy, repeated apply without
new versions, immutable conflicts, source-authoritative updates, denied source
credentials, stopped/retired Vault and missing/deleted target records. Unit tests
also cover CAS conflicts, lost acknowledgements and whole-wave validation. This
is protocol evidence, not production migration, persistent recovery or physical
TPM evidence.

Validation on 2026-10-26: `pytest -q tests/test_bao_migration.py
 tests/test_devenv_command_catalog.py` passed **50 tests, 0 failed, 0 skipped**.
`devenv tasks run tests:bao-migration-vm` passed against the final provisioning
implementation (VM driver **26.21 seconds**). Initial rehearsal failures were in
the test configuration (read-only Nixpkgs configuration) and its token leak check
(reading a deliberately removed source token); both were fixed and the complete
lane rerun. The earlier native-command catalog failures are resolved by keeping
native host commands in their own validated collection, rather than declaring
them Devenv wrappers. No production migration or activation was performed.

The accompanying broad encryption regression (OpenBao, local enrollment,
operator storage, Secure Boot controller signing, recovery provisioning and TPM
release tests) returned **126 passed, 1 failed, 0 skipped**. Its sole failure was
the command catalog observing the new `openbao-local` command before its
concurrently edited documentation existed; the subsequent focused 50-test run
passed. `tests/test_storage_cutover.py` separately passed **7 tests**.
Final `devenv tasks run docs:check`, `devenv tasks run nix-quality:check`,
`python scripts/lint_structure.py` (23 manifests) and `tracker.py validate`
(11 feature definitions) passed. Lifecycle readiness remains **0/12** and must
not be represented as a completed production release; physical acceptance and
remaining rollout integration are tracked independently.
