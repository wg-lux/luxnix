# Boot LUKS migration and recovery

Fresh installation is the default for new machines; start with the
[setup quickstart](boot-storage-quickstart.md). This reference covers the explicit
preservation workflow and retained-storage recovery. The
[current contract](https://github.com/wg-lux/luxnix/blob/main/boot-storage.yml)
owns requirements. Historical OpenBao/TPM acceptance and retired installer details
remain in the [versioned archive](https://github.com/wg-lux/luxnix/blob/39eeabdbc52af4129eafb76bfa9e8d84757ade92/docs/boot-storage-migration.md).
Repository configuration and dated reports do not establish live host acceptance.

## Shared encryption contract

Root uses LUKS2 and one operator passphrase; secondary keys live on encrypted
root, outside EFI, the initrd and Nix store. Root unlock needs no network key
service. Homes, Nix, logs and secrets belong under encrypted storage. MD arrays
assemble below LUKS; every retained Btrfs member must have encrypted backing.
Swap must be encrypted or disabled. Missing/wrong storage blocks protected writers.
No boot service formats storage or generates replacement keys.

| Role | Mapping |
| --- | --- |
| Root | `cryptroot` |
| Application volume | `luxnix-app-storage` |
| Retained secrets volume | `luxnix-secrets` |
| Encrypted swap | `cryptswap` |
| Other data/members | `luxnix-data-<mount-path>`, optionally `-member-N` |

LUKS, login, wallet and application passwords are independent. Preserve existing
application keys/salts and account hashes; storage changes do not rotate them.
Account changes follow [explicit rotation](admin-passwords.md#explicit-replacement-and-activation-safety).
SDDM presents the account chooser; boot auto-login is disabled.

### Splash unlock and generation recovery

The initrd requires a LUKS2 header on the configured root partition. Without one
it stops, and there is no plaintext fallback. The former plaintext **linear**
mapping remains only behind `plaintextRootBridge`, default off, for disposable
tests; activation is refused once that disk is encrypted.

A host whose disk is still plaintext must select `legacy-containers`. The
target-host preflight refuses any generation that does not match the physical
disk, before it reaches the boot menu. See
[Boot storage recovery](boot-storage-recovery.md).

Plymouth uses the text `details` theme. Unlock waits without an attempt or time
limit. Keep console access and a compatible boot generation. Compare
`/run/current-system`, `/run/booted-system`, the persistent system profile and
bootloader default separately after failure. Rollback cannot reverse disk
conversion, restore keys or undo application/database changes.

### Explicit password verification

On an encrypted host, use helpers from the exact reviewed candidate in a private
terminal, replacing `./result` with that candidate's path:

```sh
sudo ./result/sw/bin/luxnix-setup-root-encryption --setup-password
sudo ./result/sw/bin/luxnix-verify-boot-storage
```

These diagnose and verify; they cannot encrypt plaintext root. A private
host/UUID/header-bound receipt records verification, never the password.
`sudo luxnix-setup-boot-password --change` adds a password after verifying an
existing credential and backing up the header; it retains existing slots.
A root-only check does not prove secondary unlock or cold boot. Rebuilds do not
rotate account/wallet passwords or perform this storage conversion.

## Guided operator workflow

Run `devenv shell luxnix migrate` explicitly to preserve the existing machine.
It reads `autoconf/config.yml`; `--host`, `--config` and `--device` select reviewed
alternatives. Use `devenv shell luxnix status` to inspect progress without changing
state. `devenv shell luxnix storage <action>` and
`devenv shell boot-storage-setup` expose the administrator interface.

### Configuration and recovery media

Migration requires `root_encryption: luks2`, `installation: in-place` and
`source_retention: in-place`. `boot_storage.hosts.<host>` supplies the hardware UUID
and exact disk `path`, `serial`, `size_bytes`; `paths.nix_output` identifies the
clean durable release checkout. State is under `boot_storage.state_root`, normally
`/recovery/luxnix-state/<host>`.

Media preparation selects an existing removable ext4/XFS/Btrfs filesystem,
excludes system/target disks, requires metadata space and mounts it at `/recovery`.
Ambiguous selection requires `--device`; it never formats existing media. This
is journal storage, not a data backup. Plaintext credentials require separate
encrypted custody even if non-secret evidence uses an unencrypted filesystem.

Planning pins the revision, lockfile, closure and hardware. Before installer boot,
retain those artifacts and the journal independently of target disks at their
planned paths. Installer state must be root-owned/private, outside `/mnt` and
target disks. Use the reviewed root Python environment, never `sudo devenv`.
Target-backed Nix stores, active swap, mounted targets and conflicting mappings
block the operation.

### Replacing a saved plan

Status, next-step inspection, verification and execution previews are read-only.
Explicit planning or the migration guide can replace an outdated **unstarted**
plan, retaining the previous directory as `<state>.superseded-<id>`. Replacement
and execution share a stable lock held through the complete operation, including
surviving conversion children. Started work
is never replaced. A pending install with no provisioning journal, or phase
`planned`, has not started; inspect `progress.json` and `provision.json` if unsure.
Any other result requires [recovery review](#interrupted-setup). Do not edit plan
revisions, receipts or journals to fit a new checkout. A replacement needs fresh
preflight and recovery evidence; prior reviews do not carry over.

### In-place root encryption

The converter supports one plaintext Btrfs root. MD arrays, other root filesystems
and additional encrypted partitions need separate support. On trusted installer
media, `python -m lx_administration.storage.boot_setup run --apply` asks for typed
`ENCRYPT IN PLACE` approval and passphrases, then:

1. Tests container credentials and verifies that their data fits on root.
2. Shrinks Btrfs by 32 MiB and runs `cryptsetup reencrypt --encrypt`.
3. Verifies filesystem UUID and Btrfs consistency, then mounts encrypted root.
4. Removes the obsolete plaintext swap signature, reporting any required manual
   completion rather than treating swap as durable data.
5. Opens retained containers read-only, copies and compares their logical contents,
   and publishes verified directories. Pre-existing underlying data is retained
   as `<path>.pre-consolidation`; completed copies are not repeated.
6. Records password verification, then prepares access and installs the system
   through the separate reviewed steps.

Use letters a-x, digits and spaces for the conversion passphrase to avoid boot
keyboard-layout differences. Keep it independently. An interruption resumes from
the LUKS2 header with the same journal; never format or restart from scratch.
Containers remain until acceptance. Afterwards `devenv shell luxnix retire-containers`
previews removal; `--apply` requires typed approval and rejects attached or
unconsolidated containers. It does not delete their vault recovery records.

### Recovery and secret preflight

Make and test a consistent data backup before conversion. Preserve LUKS headers,
original application master keys, historical keys/salts and account credentials
on independent encrypted media. Inventory nested mounts and all database paths.
Quiesce writers before database dumps/filesystem capture; an ordinary live PGDATA
copy is not a valid database backup. Restore to an isolated encrypted target,
query PostgreSQL and decrypt old media before claiming recoverability.

The guide records a named decision to proceed without a backup as `risk-accepted`,
confirmed with `ACKNOWLEDGED`. It is not a verified backup or proof of recovery.
A recorded restore test is `restore-tested` and remains operator-reported;
the guide cannot prove restoration from a path or a confirmation. Older notes
without a distinct backup outcome leave backup verification unknown. Credential
custody and a passing secret preflight do not establish a consistent data backup.

The guide prepares or opens custody without reformatting an existing file,
copies only missing credentials and verifies reopening. Custom custody uses:

```sh
devenv shell luxnix storage preflight --custody <private-encrypted-directory>
```

For a controller holding `~/.lxv`, additionally use
`--vault-key-custody <independent-key-copy>` on a different physical disk from
custody. The key must decrypt the copied vault without the source machine.
Custody must be private, encrypted and independent of every target disk.
Close/reopen it and rerun checks; access through an already-open mapping alone
does not prove the recovery credential works. Never rerun `luksFormat` on an
existing custody file, even when its currently open mapping still works.

Preflight derives required credentials from the evaluated host: admin/client
hashes, application keys and every salt generation, recipient private keys,
OpenVPN/SOPS identities and keys for volumes outside the selected disks. It tests
the admin password privately, compares custody copies, and authenticates controller
vault recovery. Copies live beneath `<custody>/<host>/secrets/<original-path>`;
controller vault copies use `<custody>/controller/.lxv`. Unlock missing source
containers first. Regenerating a missing historical key is not recovery.

The receipt expires after 24 hours and is bound to the plan; failure invalidates
it. Preflight does not prove a data restore or the future root passphrase.
[Credential backup](credential-backup.md) provides authenticated archives but
neither replaces full data backup nor the custody-copy comparison. Vault/OpenBao
server data and unseal recovery require [Vault Server Rebuild](vault-server-rebuild.md).
Keep passwords, hashes and key bytes out of notes and logs.

### Evidence and advanced interface

`next` names required checks. `review --assessor <name> --report <private-notes>`
records only checks actually performed. `devenv shell boot-storage-migration`
provides `plan`, `status`, `attest`, `prepare-access`, `check` and `install` for
reviewed automation. Its native specification includes version, host, checkout,
hardware UUID, encryption/migration intent and exact disk identities.

In-place stages are `recovery`, `prepared`, then physical `acceptance`. Evidence
contains exactly `schema_version: 1`, `plan_id`, `stage`, `checks` and nonempty
`artifacts` with private absolute paths. Hashes bind artifacts to the plan;
pre-install reviews expire after 24 hours. Missing evidence pauses work, never
creates a successful assessment.

From trusted media, `check --stage provision` validates prerequisites. After
conversion, `prepare-access` preserves/restores the configured admin hash and
optionally creates the dedicated initrd SSH identity. Record prepared evidence
and pass `check --stage install`. The install-only action verifies hardware,
mounts, keys and access before and after `nixos-install`, under a machine-wide
lock. It does not prove live login or cold boot. Unsupported signed first
installation stays blocked; use the [signing workflow](secure-boot.md).

### Interrupted setup

Preserve `provision.json`, `progress.json`, the pinned artifacts and backups.
The journal is execution evidence, **not a backup**. Inspect hardware and repair
or mount the intended complete encrypted layout from trusted media. Preview,
then explicitly accept it:

```sh
python -m lx_administration.storage.boot_setup recover --assessor <admin>
python -m lx_administration.storage.boot_setup recover --assessor <admin> --apply
```

Recovery rechecks identity, filesystems and evidence and requires exact terminal
confirmation. Uncertain layouts remain blocked. Interrupted system installation
requires `install-recovery` assessment before `boot-storage-migration install
--retry-interrupted`; never delete a journal to authorize retry. Old plaintext
boot generations cannot open a converted root. Fresh-install journals have a
separate refusal/review path in the [quickstart](boot-storage-quickstart.md).

### Remote SSH root unlock

Opt in through canonical host YAML and regenerate: set
`luxnix.storage.operatorUnlocked.remoteUnlock` with exact interface/NIC modules,
static CIDR address, optional gateway, management `allowedSources` and dedicated
Ed25519 `authorizedKeys`. Port 2222 allows only interactive unlock, without shell,
forwarding or inherited login keys. Console unlock remains available.
`prepare-access` creates the dedicated host identity once and prints its public
key; pin it through the trusted installer channel before `ssh -tt -p 2222` with
strict host-key checking. Test the actual management network and recovery console.

The dedicated private key is included in the **unencrypted initrd**; never reuse
normal host/login keys. Controller-held signing currently rejects this combination
with host-local initrd secrets. Do not weaken that assertion or downgrade Secure
Boot to enable it. Neither this mode nor TPM enrollment is the fresh-install default.

### Readiness observations versus admission

`devenv shell storage-readiness --limit <host>` collects observations. Private
request YAML can select `storage_readiness_mode: admit`, the expected host/layout
and exact attached serials. Admission also checks probes, boot generations and
no active swap; it changes nothing. Optional full reports are sensitive,
gitignored files under `cmdb/storage-readiness/` with private permissions.
Collection success is not admission, restore proof or erasure approval.

## Snapshot backups from the existing gc-09 and gc-10 installations

After connectivity checks, use `devenv shell storage-migration-snapshot` with an
explicit supported host, unique snapshot ID, root become user and private sudo
password file. It serializes operations, stops declared writers, freezes mounted
inner filesystems, retains read-only Btrfs snapshots and restores only previously
active services. Coverage lives in `lx_administration/storage/migration-policy.yml`;
review it when hosts, paths or writers change. Snapshots need free space and do
not include unrelated subvolumes, external export disks, GPT/EFI or controller
vault custody. They are not whole-disk images or database restore acceptance.

Completed retries verify original identities. Partial runs are retained, never
combined with another capture window. `migration_snapshot_action=status` inspects
the journal; `migration_snapshot_action=recover` retries journaled thaw/service
recovery after supervisor failure. Changed identities, uncertain snapshots or
failed thaw keep recovery blocked. Do not delete journals, locks or snapshots.

Use `devenv shell storage-recovery-custody prepare` with dedicated native age
identities on encrypted controller storage and independent encrypted custodian
media. It creates only missing identities and tests each against a challenge;
`verify` repeats checks without key generation. Also test off-machine media access.
`devenv shell storage-migration-backup` accepts the exact backup mountpoint, host,
snapshot ID and both identities; see the command catalog for its arguments.
It reads only recorded snapshots, encrypts streams to both recipients and fully
authenticates each copy before publication. Backup media may hold ciphertext,
but must not hold unencrypted private identities.

`.partial` and `.unverified` files are not accepted backups. Receipts bind source,
producer, snapshot identities and recipients; drift blocks reuse. Explicit
`--recover-existing` authenticates existing archives against the current source
before adoption. Host-local verification supplies each identity through stdin,
never a plaintext host file. Preserve old native/SSH identities needed by existing
archives; new backups do not rewrite them. Restore into an empty isolated encrypted
Btrfs directory using authenticated `age` decryption, decompression and `btrfs
receive`, checking every pipeline exit status, then validate database and old media.

### Full-disk image of the original NVMe

For a complete recovery image, shut down and boot trusted media. Identify the
source by serial, keep all source partitions unmounted, disable swap/automounting
and use an independently identified destination. Stream the whole device, including
GPT/EFI, into a new encrypted archive. Check every pipeline status and compare raw
byte count/hash with a full decrypt/decompress verification. Never write plaintext
images or recovery identities onto unencrypted backup media. Keep failed artifacts
for review. Restoration can discard newer writes and needs separate authorization.

## Acceptance, recovery and rollback limits

Cold boot offline: one root unlock, automatic secondary unlock, local SOPS where
used, administrator login/sudo/SSH and database/application startup must work.
Query restored data and decrypt old media. Test independent recovery credentials.
On a disposable copy, absent data disks or invalid secondary keys must block
writes under missing mounts. Check retained key identity across activation,
reboots and a normal signed update. Record physical evidence separately from VM
results; successful builds or service starts are insufficient.

Missing mappings or keys call for identity/custody investigation, never formatting
or replacement key generation. Root passwords cannot decrypt application backups
without their separate application keys. In-place conversion has no old disk to
return to: the tested backup is rollback, and restoring it loses later writes
unless preserved. Retain backups and containers until signed-off acceptance.

## Temporary compatibility and removal

Existing `legacy-containers` hosts, including the explicit gc-10 exception,
retain their container UUIDs, bind maps, original keys and recovery tools. Normal
rebuilds do not migrate them. gc-10's missing recovery console and unsupported
multi-disk conversion are blockers, not consent to erase. One-member RAID1 offers
no redundancy; adding a mirror requires reviewed MD growth, never rerunning Disko.
See [legacy recovery](legacy-storage-recovery.md) for its guarded activation and
backup procedures. Plaintext application startup and disk swap remain prohibited.

Select compatibility only through canonical host inventory, validate with
`devenv tasks run autoconf:check`, render/compare and regenerate with
`devenv tasks run autoconf:generate`. Container `migration.enable` governs copying,
not physical root acceptance. Remove exceptions and recovery material only after
supported conversion, physical acceptance and the retention decision. Configuration
changes never constitute proof that gc-09, gc-10 or another live host was migrated.

<a id="reprovision-and-restore-explicit-destructive-operator-action"></a>
## Retired destructive installation paths

Old erase/restore plans are retained evidence, not executable approval. Never edit
them to bypass rejection. New fresh installation uses its own reviewed bundle and
explicit operation-specific consent; it cannot reuse preservation journals.
Unsupported preservation layouts stop without a formatting fallback.

## Coordinated hub snapshots

The gs-02 coordinator stops declared application/database writers, creates a fresh
PostgreSQL dump in root-controlled `/run`, copies encrypted media, verifies checksums
and atomically publishes the restore point. Failure prevents publication. Its
journal restores only previously active units; failed recovery retains
`/run/luxnix-hub-backup/recovery.json` for `luxnix-hub-backup recover`. Do not delete
it to bypass recovery. External/manual writers need separate quiescence.
Destinations must be non-overlapping real paths beneath encrypted storage, without
symlink/traversal escapes. Restore and cold-boot acceptance remain mandatory.

## Repository verification and physical evidence

Use the focused Python/storage suites in [Testing](testing-nixtests.md), plus:

```sh
nix build .#checks.x86_64-linux.boot-storage-fresh --no-link -L
nix build .#checks.x86_64-linux.boot-storage-in-place --no-link -L
nix build .#checks.x86_64-linux.hub-backup --no-link -L
devenv tasks run nix-quality:check
devenv tasks run docs:check
python scripts/lint_structure.py
```

VMs use disposable media and synthetic credentials. They do not prove physical
fleet boot, production Secure Boot custody or clinical application restoration.
Readiness and evidence stay in the feature tracker, not historical test counts.
