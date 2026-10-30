> Storage layout update: [Boot LUKS migration](boot-storage-migration.md) is the
> current fleet design. Container unlock, login unlock and local OpenBao storage
> enrollment below apply only to explicit `legacy-containers` recovery mode.
> Existing identity provisioning remains independent.


# OpenBao target architecture: local volume unlock, central identity provisioning

Status: partially implemented, not accepted for production unattended unlock.
The shared EndoReg profile supports operator-controlled local OpenBao with
`seal = "passphrase"`, uniformly across hosts. This is not TPM auto-unseal and
does not satisfy unattended-unlock gates. See [seal operation](openbao-local.md#seal-selection-and-passphrase-operation).
Architecture decided on 2026-10-26; rollout revised on 2026-10-27 from the
owner-supplied offline-theft recommendations. Acceptance criteria: `boot-encryption-acceptance.yml` (schema 1.3),
whose `evidence_policy` defines which evidence counts. Readiness stays in the
secret lifecycle feature tracker.

## Rollout gates (2026-10-27)

Offline theft protection is the primary objective: modifying boot components,
root or the Nix store must not give altered code volume keys. Production
unattended unlock requires Secure Boot **and authenticated executed system
contents**. A signed UKI or PCR 7 alone cannot pass ENC-09. The updated catalog
removes the alternative of accepting that gap as the production default.

The ordered work, responsible roles and exit evidence are canonical in
`boot-encryption-acceptance.yml` under `rollout_plan`:

| Gate | Required outcome |
|---|---|
| R0: baseline and custody | Verify effective live unlock, firmware keys, existing credentials and recovery outside both gs-02 and the target. |
| R1: integrity spike | Map the whole trusted execution path and writable overrides; demonstrate authenticated contents, safe updates/rollbacks and failure before release. |
| R2: production enforcement | Physical TPM and live Secure Boot checks at enrollment, activation and before installer disk changes; integrate external signing and interruption handling. |
| R3: lock and recovery | Ordered close, explicit recovery/re-seed, independent restore and salt custody/receipt gates. |
| R4: physical references | gc-09 pilot for its class, then every other class; tamper, outage, cold boot and recovery tests with named assessors. |
| R5: fleet waves | Same group profile, bounded inventory waves and stop on failure; no premature group switch or gc-10 production exception. |

The working tree currently selects passphrase unlock throughout the fleet and
leaves Secure Boot disabled by default. gc-10 has enrollment tooling enabled;
this does not prove enrollment or live settings. Keep operator-controlled unlock
until the gates pass. Existing enrollment, adoption, provisioning and controller
signing are implementation progress, not physical acceptance.

The current pilot target is gc-09. Safety policy is owned by the shared
`roles.endoreg-client` role, including its GPU and hub consumers; the pilot has
no weaker host override. The role requires encrypted storage and rejects
unattended unlock while authenticated system and application runtime integration
is missing. TPM-mode enrollment and local OpenBao startup also reject disabled Secure
Boot, unusable TPMs, detected virtualization and unrecognized platform TPM drivers.
These checks do not establish hardware attestation or approval of firmware keys.

Independent local unlock during a gs-02 outage remains the existing decision.
The target unattended TPM profile also permits an intact approved stolen host
to unlock: there is no offline
remote kill switch. Console, recovery-shell, external-boot and DMA/debug access
therefore need physical testing. The currently supported passphrase-seal profile
requires an operator factor and does not provide unattended unlock. Requiring
online permission would change the independent-unlock architecture and needs
an explicit owner decision.

No PCR set, integrity tool or image layout is selected by this update. The
options below remain spike candidates. Recovery custody currently documented on
gs-02 is insufficient for the new independent-copy gate: verify an encrypted
copy outside both gs-02 and the target, with recoverable decryption custody.

## Roles

| Instance | Where | Holds | Needed at boot |
|---|---|---|---|
| Local OpenBao | Every host in `operator_unlocked_secrets`, including gs-02 for its own volumes | One random unlock secret per LUKS container of this host | Yes, before any operator-unlocked volume opens |
| Hub OpenBao | gs-02 | Host identities (TPM certificate roles), policies, PKI, center salts for allowlisted shared centers, provisioning audit | No; only for enrollment, issuance, center salt delivery and revocation |
| Admin vault and emergency export | Operator workstation and a separate recovery host | LUKS recovery passphrases, local seal-key escrow | No; recovery only |

The hub OpenBao takes over the identity provisioning that HashiCorp Vault does
today:
- machine enrollment, currently based on AppRole SecretIDs (`hub_enrollment`);
- hub PKI;
- delivery of center identity salts to hosts of allowlisted shared centers.

Vault stays authoritative for each of these until a cataloged migration wave
moves it (see `docs/openbao.md`).

## Fixed decisions

- **A TPM is mandatory.** Installation, activation and boot fail when no
  usable TPM 2.0 is present. There is no automatic downgrade. Recovery is an
  explicit operator command, never an `unlockMethod` value that inventory can
  select.
- **Volume unlock is local and unattended.** It does not depend on gs-02, the
  VPN or DNS.
- **Identity salts stay source-local** as defined by `identity_salt` in
  `secrets-management.yml`. The hub delivers center salts only for allowlisted
  shared centers, which is the current Vault job. Machine salts, patient hashes
  and examination hashes never go to the hub.

## Local OpenBao (per host)

**Storage.** Raft lives on the root filesystem at `/var/lib/openbao-local`. It
cannot live on an operator-unlocked volume, because it is needed to open those
volumes. Confidentiality comes from the OpenBao barrier.

**Seal.** OpenBao static seal. The 32-byte key comes from
`LoadCredentialEncrypted`, created with `systemd-creds encrypt
--with-key=tpm2` and an explicit PCR policy. A credential encrypted only with
the host key (`--with-key=host`, or `auto` without a TPM) must be rejected
before OpenBao starts. That key is `/var/lib/systemd/credential.secret` on the
same unencrypted root, so a disk copy would decrypt it. The seal key is
escrowed to the admin vault and the emergency export before the first
initialization. Static seal support in 2.6.4 has recorded VM evidence in
[local implementation](openbao-local.md); physical acceptance remains open.

**Access.** Clients use a private Unix socket. On 2026-10-26 the repository
owner approved a TCP listener solely inside a private network namespace:
OpenBao 2.6.4 otherwise cannot synthesize the Raft cluster addresses and fails
initialization. `PrivateNetwork=true` isolates API port 8310 and cluster port
8311 from the host network. This exception does not permit a host-visible TCP
API. See [local implementation](openbao-local.md). The unlock path holds
a TPM-bound read-only credential limited to `volume-release/data/<host>/*`.
Creating records uses a separate provisioning credential that is never present
at boot.

**Records.** `volume-release/<host>/<volume>/<luks-uuid>` holds a random
256-bit keyslot secret, distinct from the recovery passphrase. It is written
once (CAS 0) and verified by reading it back. The record key is the inventory
host name; `machine-id` is stored only as an attribute because it changes on
reinstall.

**Disposable store.** Losing the local store (TPM failure, TPM clear, board
swap) never loses data. The volumes open with the escrowed recovery passphrase.
A cataloged re-seed command then builds a new store and new keyslots, and it
removes the old OpenBao keyslot only after the new one test-opens.

### Boot ordering

1. TPM check. It fails the unit; it never skips it through `Condition*`.
2. Credential check. A credential that is not TPM2-sealed is rejected.
3. `openbao.service` starts and auto-unseals.
4. The unlock unit waits, within the 90-second budget, until `sys/seal-status`
   reports `sealed=false`. Service readiness alone is not "unsealed".
5. The unlock unit reads each record and passes it to
   `cryptsetup open --key-file=-`. Distinct failure reasons are:
   `tpm-missing`, `credential-not-tpm`, `bao-sealed`, `record-missing`,
   `keyslot-rejected`. There is no prompt, TPM token or passphrase fallback.
6. Mount verification, binds and guarded services, as today.

Shutdown runs in reverse: writers, binds, filesystems and LUKS close first,
and only then does OpenBao stop.

### Provisioning a new container

Each phase is idempotent. A rerun resumes at the first incomplete phase; a
permanent stop is a defect.

1. **preflight:** TPM present, Secure Boot active, local OpenBao initialized
   and unsealed.
2. **escrow:** generate the recovery passphrase, then authenticate it in the
   admin vault and the emergency export (existing `provision.py` flow).
3. **record:** generate the keyslot secret, write it to local OpenBao with
   CAS 0, and read it back.
4. **format:** `luksFormat` with the recovery passphrase, but only if the
   container file does not exist yet.
5. **keyslot:** `luksAddKey` with the keyslot secret, only if it does not open
   the container yet. No `systemd-tpm2` token.
6. **filesystem:** `mkfs` only on a verified empty mapping.
7. **receipt:** test-open with both secrets, then write the receipt.

A container with the expected UUID that opens with the escrowed passphrase is
always resumable. It is never treated as "never reformat, stuck".

### Converting an existing container

1. Escrow, or verify the existing escrow of, the current recovery passphrase.
2. Write the record and add the OpenBao keyslot, then test-open it.
3. Remove every `systemd-tpm2` token.
4. Keep the recovery keyslot.

The plan shows each keyslot and token change before execution.

### Earlier rollout decisions (owner, 2026-10-26)

The R0-R5 gates above now govern production release. The VM integration
threshold below is necessary but no longer sufficient to switch the group.

- **Missing containers are created on the next update,** but only through the
  cataloged deploy command. The controller escrows the recovery passphrase to
  the admin vault and the emergency export first. The host then creates the
  container and stores its unlock secret in the TPM-sealed local OpenBao. A
  plain boot, rebuild or activation never creates a container.
- **gc-10 keeps its existing containers** and receives a dedicated OpenBao
  keyslot at adoption (superseding decision, same day). The record holds a
  random 256-bit secret, never the recovery passphrase. The recovery keyslot
  stays, and `systemd-tpm2` tokens are removed. The current passphrase is
  escrowed first with `storage-provision escrow`. See
  [local enrollment](openbao-local.md#enrollment-and-volume-adoption).
- **Hosts without a usable TPM** abort the update before any change.
- **Data moves by background pre-copy and a short stop**
  (`lx_administration/storage/cutover.py`):
  1. While writers run, the data is copied repeatedly into a private staging
     copy next to the destination.
  2. All writers stop.
  3. A final `rsync --checksum --delete` makes the staging copy exact, and a
     dry run must report no difference.
  4. The staging copy is renamed into place and the receipt is written.
  5. Binds activate, then the writers start.

  If the final copy fails, the binds stay inactive and the writers restart on
  the untouched source.
- **The inventory switch comes last.** The group switches to
  `unlockMethod = "local-openbao"` only after enrollment, deploy-time
  provisioning and cutover are integrated and VM-tested. Switching earlier
  would boot hosts with locked volumes.

## Hub OpenBao (gs-02)

- **Authentication.** Hosts log in with their TPM-resident certificate
  (`luxnix-tpm-release`). Each host has one cert role and policy and gets
  single-use, short-lived tokens. This replaces bearer AppRole SecretIDs.
- **Center salts.** Only for centers in the shared-center allowlist, under
  `identity-salts/center/<center>/<generation>`, create-only. Other centers
  get neither path nor policy.
- **State.** The hub state is on a gs-02 volume that the gs-02 local OpenBao
  opens. The hub instance itself uses Shamir with custodians unless decided
  otherwise. Clients keep booting while it is sealed.
- **Migration from Vault.** One cataloged wave: freeze writers, copy, verify
  values without logging them, switch readers, then retire the Vault path.
  There are no dual writes.

## Identity salt durability (owner decision open)

All three local salt copies sit on `luxnix-secrets`, which is one failure
domain. The hub backup excludes them. The source-local contract allows a second
local failure domain, for example a copy on `luxnix-app-storage`, which is a
different disk on gc-10. Escrowing machine salts into recovery custody changes
the contract and needs the center identity custodian and the endoreg-db
maintainer. Until the owners decide, `lx-annotate-identity-salt-migration` runs
only after a receipt proves the active generation exists, verified, in two
failure domains.

## Target code structure (no spaghetti)

The current code switches on `unlockMethod` and on `if local then` throughout
one service module and one migration class. The production structure has one
owner per concern and no dead strategies.

| Unit | Responsibility | Replaces |
|---|---|---|
| `modules/nixos/luxnix/openbao/local.nix` | Local instance: Raft on root, static seal, socket, credential guard, TPM assert | `local` branches in `openbao/default.nix` |
| `modules/nixos/luxnix/openbao/hub.nix` | Hub instance: TLS listener, cert auth, encrypted-mount guard, audit | Non-local branches |
| `modules/nixos/luxnix/openbao/common.nix` | Shared audit, storage guard and package; no role logic | Duplicated settings |
| `lx_administration/storage/bao.py` | One OpenBao client with two transports (Unix socket locally, mTLS with TPM key at the hub). Response validation, no secrets in argv or logs | The `local_openbao.py` prototype and the HTTP part of `tpm_release.py` |
| `lx_administration/storage/tpm_identity.py` | TPM identity create and check (from `tpm_release.py`) | Unchanged logic, separate module |
| `lx_administration/storage/unlock.py` | One strategy: wait for unseal, read record, `cryptsetup open` | Branches of `Migration.unlock()` |
| `lx_administration/storage/provision_phases.py` | The phased, resumable state machine above with one receipt format | `Migration.provision()` |
| `lx_administration/storage/operator_migration.py` | Data copy and receipts only | Mixed unlock and provision code |
| `luxnix-operator-storage recover <volume>` | Explicit operator recovery with the passphrase | `unlockMethod = "passphrase"` |

The `passphrase` and `tpm2` unlock branches and `enroll-tpm2` are removed from
the automatic path, not kept as dormant options. Group inventory sets
`luxnix.storage.operatorUnlocked.profile = "local-openbao"` and nothing else.

## Evidence rules for this work

The full policy is `evidence_policy` in the catalog. The rules that matter most
for agents:

- Criteria change only through a dated owner decision. They are never adjusted
  to fit an implementation.
- Boot, TPM binding, cold start, recovery and tamper claims need hardware
  evidence. VM, swtpm and mocks prove logic only.
- Skipped tests are not passes. Report passed, failed and skipped separately.
- Grepping source or docs is static evidence, never functional evidence.
- Every security claim has a negative test, and blocking fixes include a
  mutation check: remove the protection and the test must fail.
- A test that enshrines a known defect is itself a finding. The current
  example is `tests/test_operator_storage_migration.py`, which asserts the
  stuck "never reformat" state.
- No raised baselines, no `--allow-partial`, `--force` or mock environment
  switches to pass a gate.
- Agents set at most `in_progress` or `blocked` in the tracker. `verified`
  needs a named human assessor.

## Consequences and accepted limits

- **No boot dependency on gs-02.** This removes the VPN and DNS cycle for
  unlock.
- **No central revocation of volume keys.** Hub revocation stops identity
  issuance and center salt reads only. A stolen powered-off device is
  protected only by the TPM binding and boot integrity.
- **ENC-09 carries the whole offline protection.** Anyone who boots the
  unmodified, Secure Boot-signed system gets the volumes. PCR 7 alone does not
  cover the root filesystem or the Nix store.
- **Every host runs an OpenBao instance.** Upgrades, root-filesystem audit
  capacity and monitoring become fleet tasks. A full audit device blocks
  requests, and therefore boot.

## Implementation review (2026-10-26)

The earlier handoff mixed implemented components with integration work. The
current code separates these contracts:

- `openbao_local.py` rejects software-only and PCR-unbound credentials and checks
  initialized, unsealed, active state before releasing a UUID-bound key.
- Enrollment, confirmation, adoption and unlock-credential rotation are exposed
  through `openbao-local`. Adoption preserves recovery and adds an independent
  OpenBao keyslot before removing legacy TPM keyslots.
- Explicit `Migration.provision` now supports local OpenBao, uses private
  unpublished allocation, and resumes authenticated LUKS state. The legacy TPM
  backend is still separately available; it is not used by local-OpenBao rollout.
- `cutover.py` is consumed by `operator_migration.py` and packaged with the Nix
  module. Pre-copy and final cutover have explicit units and the controller's
  `openbao-local rollout` command orders enrollment, custody and volume work
  before those units. Ordinary boot never provisions missing containers.
- The existing Vault-to-hub command transfers current allowlisted KV-v2 records
  with CAS and validates target-only operation. It does not migrate historical
  KV versions, PKI/auth state or change application endpoints.
- Local OpenBao escrow is indexed by inventory host with machine-id as an
  attribute. Existing volume-recovery escrow retains its machine-id namespace;
  callers verify host, container, volume and native UUID as well.

The source capabilities above are distinct from physical-host acceptance.
PCR 7 does not authenticate arbitrary root/Nix-store content, and the identity
salt copies still share a storage failure domain. The corresponding acceptance
criteria are not satisfied merely by passing enrollment or migration tests.

## Researched options for the four open decisions (2026-10-26)

These are recommendations and an implementation/test order, not new accepted
requirements. They do not change source-local salt ownership or close ENC-09.

### 1. Durable machine salts

Use an immutable generation bundle containing the stable inventory identity,
generation IDs, active/retiring references and all required historical salts.
Before activation, authenticate a second copy and perform a restore/readback
comparison. A receipt binds the exact generation to the verified destinations;
a directory's existence or a successful upload is insufficient. Never generate
a replacement when enrolled material is missing. Restore must preserve the
historical pseudonym linkage, not merely produce a readable salt file.

Within the current source-local contract, put the second encrypted copy on a
physically independent local device. Verify actual backing devices: another
LUKS container, partition, bind mount or Raft replica on the same disk is not a
second failure domain. Two local disks still share theft, fire and chassis loss.
For protection against those events, recommend a source-owned removable encrypted
offline medium kept separately. A centrally stored opaque encrypted recovery
bundle is another option, but requires the identity custodians' approval of the
ownership change; the hub must not acquire a machine-salt read/decrypt policy.
Off-site removable custody also needs the identity custodians to confirm that
it meets the source-local contract before use. Keep decryption custody independent of both the failed machine TPM and its local
OpenBao. Separate data backup retention from salt-generation retention.

Tests required before production activation: interrupted archive publication,
wrong key, ciphertext tamper, wrong host/generation, duplicate destinations on
the same disk, loss of each device, reinstall with a changed machine-id, and
restoration of historical identity recognition from the independent copy.
The new synthetic archive test exercises real authenticated encryption and loss
of the live file; it does not implement the salt-escrow workflow or prove
independent media. The automatic migration receipt gate is still implementation
work, not a consequence of writing this plan.

### 2. Where images are signed

Recommend a dedicated operator-controlled signing workstation or isolated
signing service, outside all automatically unlocked client volumes. Use a
hardware-backed signing key where the selected toolchain supports it, with
separate recovery custody. Do not install its private key on clients, and do
not let arbitrary client requests turn the signer into a general signing oracle.
The active Secure Boot task owns the concrete controller and tooling.

Build from the reviewed revision and locked inputs; approve the exact UKI,
root-image digest and release generation; sign that immutable artifact; then
verify before installing it on each ESP. Keep the firmware db signing key and
the TPM policy-signing key separate. A signed UKI can cover the kernel, initrd
and embedded command line, but does not automatically authenticate external root
contents. See [systemd-stub](https://www.freedesktop.org/software/systemd/man/latest/systemd-stub.html).

Negative tests must reject an altered artifact, wrong signer, mismatched root
image, unauthorized signing request and replay of a retired generation. A
rebuild should stage an approved signed release without pulling signing keys
onto the target. Initial enrollment and firmware recovery remain explicit steps.

### 3. Hub OpenBao unseal

Keep **Shamir 2-of-3 custodians** as the first implementable recommendation.
No single custodian or repeated submission of one share can unseal. Clients
continue local boot while the hub is sealed; fresh identity issuance waits and
reports its state. Exercise the separate hub restart/recovery objective and
custodian availability rather than claiming unattended hub recovery.

If unattended hub recovery is selected, use a separate hub seal identity bound
to gs-02's TPM, with its own escrow and integrity policy; do not reuse the local
instance's seal key. Alternatively, a dedicated transit key in the local OpenBao
can unseal the hub, with strictly scoped credentials and the one-way dependency
local OpenBao -> hub. This is supported by the
[OpenBao Transit seal](https://openbao.org/docs/2.6.x/configuration/seal/transit/),
but adds token-renewal and recovery dependencies and must never point back to the
hub itself. Keep Shamir until one alternative passes the full failure matrix.

Auto-unseal recovery shares are authorization material, **not a substitute for
the lost seal key/provider**. Back up the actual seal trust anchor and test a
restored Raft snapshot with it; recovery shares alone cannot recover such a
cluster. See [OpenBao seal/recovery semantics](https://openbao.org/docs/2.5.x/concepts/seal/).

The real OpenBao VM now checks insufficient quorum, duplicate-share submission,
partial-quorum reset, successful threshold unseal and resealing after restart.
This is a functional VM test, not gs-02 recovery evidence.

### 4. Integrity path for ENC-09

The isolated [root-integrity prototype](root-integrity-prototype.md) now has a
source trust-path map and a dedicated VM test. It uses the pinned NixOS image
builder for a verified store and volatile root. Its unsigned UKI is an assumed
trusted fixture, and its release probe is synthetic; it does not establish
production boot authentication or close ENC-09.

Recommend a verified image deployment: owner-authorized Secure Boot -> signed
UKI (kernel, initrd, embedded command line and authenticated root-image digest)
-> read-only dm-verity system image -> TPM release only under the approved boot
policy. The system image must cover the complete executed Nix closure and all
security-relevant configuration, including systemd units, authorization rules,
OpenBao, unlock helpers, dynamic libraries and interpreters. Writable state must
not override those files or supply executable plugins, environment hooks,
Python imports, startup jobs or mutable application wheels. `noexec` alone does
not prevent an interpreter from reading writable code.

[dm-verity](https://www.kernel.org/doc/html/latest/admin-guide/device-mapper/verity.html)
checks blocks against a trusted root hash; that hash must itself be authenticated.
Recomputing an attacker's hash tree must not establish trust. Verification must
be enforced before untrusted code runs, not merely through an occasional
`nix-store --verify` job. The regular-file component tests prove detection of
data/hash-tree corruption and substitution of the root; they do not establish
a kernel-enforced boot chain or protection from later writes.

Use PCR 7 for the Secure Boot policy plus a measured-UKI policy (normally PCR 11,
with explicit phase selection). Validate the exact systemd 260/NixOS path;
current upstream documentation is not proof of compatibility. Signed PCR
policies permit approved updates without arbitrary automatic reenrollment;
see [systemd TPM policies](https://www.freedesktop.org/software/systemd/man/latest/systemd-cryptenroll.html).
PCR measurements alone do not cover arbitrary later Nix-store reads.

Anti-rollback requires its own design: a signed old vulnerable image remains
signed. Test a TPM NV minimum-generation policy or an equivalent offline
monotonic mechanism, including power loss during advancement and recovery. Only
advance after a successful new boot; revoke the old generation without stranding
the host. Bind the seal release to the approved policy and minimum generation.
Until this is implemented and tested, rollback remains an ENC-09 gap.

A read-only image changes the current writable NixOS rebuild model. First build
a disposable image/VM prototype, then test each physical hardware class. Do not
claim existing btrfs/Nix-store deployments already satisfy this proposal.
IMA appraisal is an alternative only with complete signing/appraisal coverage,
immutable policy and equivalent negative tests; it is not a shortcut. Remote
attestation alone conflicts with the required independent offline cold boot.

Finally, integrity does not authenticate a person. The unchanged approved OS
will auto-unlock on a stolen machine too. Its console, recovery shell, external
boot, DMA/debug and network interfaces must prevent the thief from obtaining
privileged access. Test these paths separately. If protection against a thief
booting the intact machine requires a PIN or external factor, that conflicts
with fully unattended unlock and needs an explicit owner decision.

### Test evidence and next gates

Run `python -m pytest -q tests/test_encryption_primitives.py` for five component
cases (real crypto/verity operations, no boot acceptance). For the hub threshold
cases run the existing `devenv tasks run tests:openbao-vm`. Existing local OpenBao
and Secure Boot work retains its own tests and locks. No skipped or mocked test
is counted as hardware evidence; the encryption fixture substitutes only the
storage-location guard for disposable test keys.

The current order is R0-R5 above. Controller signing now exists in
[the Secure Boot workflow](secure-boot.md); deployment integration and physical
acceptance remain open. Prototype integrity before choosing the production
policy; resolve salt custody and verified-copy receipts before identity migration,
and exercise hub recovery in its separate migration workstream. Each gate remains open
until its positive, negative and interruption tests pass at the required class.

Validation for this research/test update (2026-10-26):

- `python -m pytest -q tests/test_encryption_primitives.py tests/lx-annotate/test_identity_salt_provisioning.py`: 55 passed, 0 failed, 0 skipped.
- `devenv tasks run tests:openbao-vm`: passed, actual OpenBao 2.6.4; driver 92.78 seconds. Derivation: `/nix/store/40ylpc1rfr4hj20adibj7dm15z8w975a-vm-test-run-openbao-release.drv`.
- `devenv tasks run nix-quality:check`, `devenv tasks run docs:check`, `python scripts/lint_structure.py`: passed (23 manifests).
- The substituted-root case includes a mutation witness: the tampered image is rejected against the pinned root, but accepted when the attacker-controlled root is trusted.
- No production salt export, signing, unseal, deployment or hardware acceptance was performed. Existing pytest temporary-directory cleanup warnings do not represent failed test cases.
