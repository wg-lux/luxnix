# Local OpenBao implementation

The target is described in [OpenBao architecture](openbao-architecture.md).
`luxnix.openbao.local.enable` now defines a separate `openbao-local.service`.
It is disabled by default pending enrollment and acceptance. Existing
`luxnix.openbao.enable` continues to define the TLS hub service. Both can run
on gs-02 with separate users, state, sockets, credentials and cluster ports.
No Vault endpoint or application key changes as a consequence of enabling the
local service.

Local Raft state lives at `/var/lib/openbao-local`, outside the containers it
will unlock. The private API socket is `/run/openbao-local/api.sock`, accessible
only by its service user and root. The static seal consumes a 32-byte key from
`LoadCredentialEncrypted`, never from Nix settings. The
[OpenBao 2.6 static seal](https://openbao.org/docs/2.6.x/configuration/seal/static/)
supports this runtime file interface. OpenBao 2.6.4 cannot initialize Raft with Unix listeners alone: its
[listener setup](https://github.com/openbao/openbao/blob/v2.6.4/command/server.go)
only synthesizes cluster addresses from TCP listeners. The operator approved
an isolated TCP listener on 2026-10-26: API port 8310 and cluster port 8311
exist inside `PrivateNetwork=true`, inaccessible from the host network
namespace. Clients still use the protected filesystem Unix socket. The internal
API uses HTTP inside that namespace; Raft cluster traffic uses OpenBao TLS.
The service is single-node and cannot join the hub Raft cluster.

The bootstrap validator permits only the systemd TPM-only credential format
and requires PCR 7 in its authenticated header. It rejects host-key, null-key,
unknown-format and PCR-unbound credentials. Header checks follow the
[systemd v260 format](https://github.com/systemd/systemd/blob/v260/src/shared/creds-util.c);
they do not replace authenticated decryption. The boot preflight only validates ciphertext. Systemd authenticates and unseals
`seal.key` when loading service credentials. Once the storage profile uses
local OpenBao, a NixOS `preSwitchChecks` gate runs the filter and a transient
systemd credential-load probe before switching (rollout stage 5 below); it never
reads plaintext into a Python process. Protected swap is checked
before the probe, and core dumps are disabled. This gate is not an installer
pre-partition check; that integration remains blocked.

Rebuilds do not restart the local service. Startup requires the existing Raft
database and never initializes a replacement store when state is missing.

## Enrollment and volume adoption

Enrollment is a cataloged, inventory-scoped operation. The controller
(`lx_administration/storage/local_enrollment.py`) drives the host tool
`luxnix-openbao-local` (`lx_administration/storage/openbao_enroll.py`) over the
pinned-host-key SSH transport of `storage-provision`. Secrets travel only on
stdin/stdout, never in arguments or logs.

```bash
devenv shell openbao-local status --limit <host-or-group>
devenv shell openbao-local enroll --limit <host-or-group> --recovery-host <host>          # plan only
devenv shell openbao-local enroll --limit <host-or-group> --recovery-host <host> --apply
devenv shell openbao-local adopt --limit <host> [--volume <volume>] --recovery-host <host> --apply
devenv shell openbao-local rotate-unlock --limit <host-or-group> --recovery-host <host> --apply
```

`--limit` accepts an inventory host or group; every selected host must belong
to `operator_unlocked_secrets`. Without `--apply` the command shows only live
status, the TPM/Secure Boot preflight and keyslot plans. A wave stops at the
first failed host. `--recovery-host` must be a separate inventory host whose
machine identity differs from both the target and the controller.

### Rollout stages

1. **Install the tool.** Deploy `luxnix.openbao.local.enable = true` with the
   existing unlock method. The service is then not started at boot, and no
   activation gate applies yet.
2. **Enroll.** `openbao-local enroll --apply` runs these phases, each live-checking
   the TPM and, where the profile declares `system.boot.secureBoot`, firmware
   Secure Boot:
   1. *seal key*: generate 32 random bytes, or reuse the escrowed ones, and escrow
      them in the admin vault (`openbao-local/<host>/seal-key.vault`) and on the
      recovery host. Then the host writes
      `/var/lib/openbao-bootstrap/seal.cred` with `--with-key=tpm2`, PCR 7 and
      `--name=seal.key`. An existing credential is compared, never replaced.
   2. *initialize*: `openbao-local-initialize.service` (never started at boot,
      asserting that no Raft database exists) creates the store, then `sys/init`
      runs. The root token and recovery key are TPM-sealed in
      `pending-enrollment.cred` before anything else happens. The host configures
      a CAS-required KV v2 mount `volume-release`, an AppRole
      `volume-unlock` (read-only on `volume-release/data/<host>/*`, 60-second
      tokens) and an AppRole `volume-provisioner` (create/read records, rotate
      unlock SecretIDs). The boot credential `volume-unlock.cred` (`--name=volume.unlock`) and
      the pending provisioner credential are TPM-sealed.
   3. *escrow*: the controller stores recovery key and provisioner credential as
      `openbao-local/<host>/enrollment.vault` in both custodies.
   4. *confirm*: the host accepts confirmation only with the SHA-256 of exactly
      the escrowed material. It verifies that the unlock credential logs in,
      destroys orphaned SecretIDs, revokes the root token and deletes the pending
      credentials.
3. **Escrow LUKS recovery.** For each volume, run `storage-provision escrow`
   (see [operator-unlocked storage](operator-unlocked-storage.md)) so that its
   current recovery passphrase is in both custodies.
4. **Adopt volumes.** `openbao-local adopt` first prints the plan (keyslots,
   tokens, changes). With `--apply` it re-authenticates the recovery escrow, test-opens
   with the recovery passphrase, writes a random 256-bit record once (CAS 0) at
   `volume-release/data/<host>/<volume>/<luks-uuid>`, adds exactly one keyslot
   for it (identified by test-open, so an interrupted run never adds a second),
   marks it with a `luxnix-openbao` token, removes every `systemd-tpm2` token
   and its keyslot, and test-opens both remaining secrets again. Recovery
   keyslots, data and UUIDs remain unchanged. Missing or UUID-mismatched
   containers are refused; adoption never formats or provisions.
5. **Switch the profile.** Set `storage.operatorUnlocked.unlockMethod =
   "local-openbao"` (with declared LUKS UUIDs).
   `openbao-local.service` is then wanted at boot, and the pre-switch gate
   `openbaoLocalPreflight` refuses activation with a named reason:
   `tpm-missing`, `secure-boot-disabled`, `not-enrolled`, `escrow-unconfirmed`,
   `credential-not-tpm` or `credential-rejected`. It checks the live TPM, the
   firmware, the store, both credential headers, and a transient systemd load of
   both credentials. That last check proves authenticated TPM decryption without
   reading plaintext into a script.

Every phase is idempotent and resumable: repeated runs neither add keyslots,
records or SecretIDs nor change data. Host mutations hold the
`/run/lock/luxnix-operator-migration` lock (shared with the storage helper), and
concurrent attempts fail with `conflict`. Controller runs serialize on
`openbao-local/.lock` in the admin vault. Existing escrow records are never
replaced; a conflicting record stops the run.

### Integrated deployment

`devenv shell openbao-local rollout --limit <host-or-group> --recovery-host <host>`
plans enrollment and every declared volume. Add `--apply` to enroll, authenticate
recovery custody, provision missing containers or adopt existing ones, and start
background pre-copy. Add `--cutover` for the final writer stop, checksum-verified
copy, bind activation and writer restart. Use all declared volumes together;
`--volume` remains an adoption-only selector. Existing volumes require their
current passphrase to have been escrowed first. See the
[storage rollout](operator-unlocked-storage.md#separately-authorized-migration)
for the complete command and recovery behavior.

The host provisioning backend now supports local OpenBao independently of the
boot unlock setting. It never enrolls a `systemd-tpm2` token for that backend.
The provisioning credential is loaded from controller escrow and sent only for
the explicit deployment operation; it is not installed as a boot credential.

### Boot unlock

Each unlock unit loads the TPM-encrypted `volume.unlock` AppRole credential.
It waits at most 60 seconds for initialized, unsealed and active state, logs in
for a single-use token, reads exactly
`volume-release/data/<hostname>/<volume>/<luks-uuid>` and revokes the token.
Records must contain the matching `luks_uuid` and a base64 `key` decoding to 32
bytes. Cryptsetup receives the key on stdin. A missing, denied or malformed
record fails without fallback. The whole unit has a 90-second timeout. Neither
the root token nor the provisioner credential is ever present at boot.

`rotate-unlock` issues a new unlock SecretID with the escrowed provisioner
credential. It seals the new SecretID, proves that it logs in, replaces the
credential atomically and then destroys every other unlock SecretID.

### Interrupted initialization

If a run stops after `sys/init` but before `pending-enrollment.cred` is
written, the host reports `interrupted-initialization`. The store then holds no
data, but its recovery key was never escrowed, so it is not usable. Enrollment
never deletes state. An operator stops `openbao-local.service`, moves
`/var/lib/openbao-local` aside for inspection and reruns `enroll`. The escrowed
seal key is reused. Any other stop resumes automatically on rerun.

### Not yet covered

- Ordered lock and shutdown (writers, binds, LUKS, then OpenBao); recovery
  and re-seed commands; fleet status aggregation with hub state (W2).
- Installer pre-partition TPM gating (W3), hardware acceptance kit (W5) and
  Vault migration (W4).
- Software-TPM rejection in production (ENC-06 hardware) is not implemented;
  `systemd-creds has-tpm2` accepts swtpm with UEFI firmware.
- PCR 7 alone is not root/Nix-store integrity (ENC-09).

These are release blockers. Successful VM runs and parser tests do not
establish hardware or migration acceptance.

## Vault migration preparation

Keep the source Vault authoritative until the [migration gates](openbao.md#ordered-migration-gates)
pass. The local service owns volume keys; the TLS hub owns central identity.
Neither service should open the Vault data directory. Use a separate target,
preserve application key bytes, verify independent recovery, and rehearse the
actual consumers before switching endpoints or issuing replacement credentials.
The Ansible admin vault remains independent recovery custody.

## Verification recorded on 2026-10-26 (enrollment)

`devenv tasks run tests:openbao-local-vm` drives the real host tool on a
UEFI guest with swtpm. The run took 166.92 seconds of VM script time. It covers
these cases:

- Explicit Secure Boot policy is refused on a guest without Secure Boot.
- Phase ordering, seal idempotence and refusal to replace the seal key.
- Rejection of a concurrent mutation.
- Identical escrow material after a resumed `initialize`.
- Refusal of a wrong confirmation digest, then root token revocation.
- Refusal to reinitialize.
- Adoption of a pre-existing container with a recovery passphrase and a PCR 7
  `systemd-tpm2` token, run three times with one identical keyslot. The TPM
  slot is removed, the recovery slot kept, and the UUID and payload hash are
  unchanged.
- Refusal of a wrong recovery passphrase or UUID.
- No release of records for another host, volume or UUID.
- Boot unlock through the unit before and after an OpenBao restart and after
  `rotate-unlock`. The old SecretID is rejected, and a provisioner SecretID does
  not work for the unlock role.
- With the Raft database missing, both the service and the unlock unit fail and
  no mapping appears. Unlock works again after the database is restored.
- A copied seal credential does not decrypt on a second TPM.

Unit tests (`tests/test_openbao_enroll.py`, `tests/test_local_enrollment.py`)
cover failure ordering and escrow-before-use with real Ansible vault
encryption. Mutation probes went red for each of these removed protections:
the confirmation digest, the Secure Boot check, seal non-replacement, the
mutation lock and export verification.

This is **VM and unit evidence** only, not physical TPM, cold-boot, recovery or
fleet acceptance.

## Verification recorded on 2026-10-26 (bootstrap prototype)

Historical record. The prototype used a hand-created `volume.token` and is superseded
by the AppRole enrollment above.

`devenv tasks run tests:openbao-local-vm` passed (52.43 seconds in the VM
script). It verifies real systemd TPM/PCR-bound credentials, rejection of
host-key and PCR-unbound credentials, failure on a second TPM, the actual
hardened local service, namespace isolation, UUID-bound API reads and actual
LUKS unlock before and after an OpenBao restart. A missing Raft database blocks
startup. Fixtures and all key material are disposable. This is **VM evidence**,
not physical hardware, recovery, cold-boot or fleet acceptance.

`devenv tasks run tests:openbao-vm` also passed (cached result for the current
hub test derivation). `devenv tasks run docs:check nix-quality:check` and
`python scripts/lint_structure.py` passed. The command-catalog tests still have
two existing failures because native `rebuild-host-switch` / `rebuild-host-boot`
entries conflict with tests expecting Devenv wrappers. Tracker validation
passes; `tracker.py check luxnix_secret_lifecycle_readiness` remains nonzero at
0/13. No acceptance criterion has been marked verified and no host was changed.

The final expanded regression run was interrupted by filesystem failures:
`pytest -q tests/test_openbao_local.py tests/test_openbao.py
 tests/test_operator_storage_migration.py tests/test_operator_unlocked_storage.py`
reported 35 passed, 5 failed and 6 setup errors before interruption. Failures
include ENOSPC during atomic writes and Nix source copying, plus missing Nix
store sources. A final Devenv rerun also failed creating its GC root. These are
recorded failures, not waived results. Once atomic writes worked again, the
same expanded command passed **47 tests in 192.30 seconds**, with no failures
or skips. `devenv tasks run docs:check nix-quality:check` also passed on retry.
Structure validation and whitespace checks pass. No cleanup or filesystem
repair was performed; the cause of the transient storage failure was not
resolved by this work.
