# Boot LUKS storage: migration and recovery

For installation commands, use the [four-step checklist](boot-storage-quickstart.md).
This reference covers layout, evidence gates, retained-data migration and recovery.
Host reports describe dated observations; live checks and `boot-encryption-acceptance.yml`
determine whether a host is accepted.

## Architecture and scope

- New clients and servers use `layout = "boot-luks"`: EFI, LUKS2 root, filesystem.
  Root protects homes, `/nix`, logs, service secrets and secondary-volume keyfiles.
- Root unlock requires an operator passphrase. Secondary filesystems unlock from
  private keys on encrypted root; keys never belong in EFI, the initrd or Nix store.
  Root unlock needs neither Git nor a network key service.
- MD RAID assembles below LUKS2. Retained multi-device Btrfs requires encryption on
  every member. Disk swap must be encrypted or disabled.
- Missing storage blocks its consumers. Verification checks all filesystem members,
  mount/subvolume identity, LUKS2, secondary keys and active swap.
- A rebuild cannot encrypt plaintext root. Never bypass pre-switch checks or create
  an unrelated mapper to satisfy them. No boot unit formats disks or generates keys.
- Application encryption, original keys/salts, backup encryption and
  [Secure Boot](secure-boot.md) remain separate requirements.

### Shared encryption contract

| Role | Mapping or behavior |
| --- | --- |
| Root | `cryptroot`; local Plymouth passphrase prompt |
| Separate application storage | `luxnix-app-storage` |
| Retained secrets container | `luxnix-secrets` |
| Separate encrypted swap | `cryptswap` |
| Desktop | SDDM account chooser; `roles.desktop.addons.plasma.bootAutoLogin = false` fleet-wide |
| Headless server | Console unlock or explicitly configured [restricted initrd SSH](#remote-ssh-root-unlock) |

LUKS, Linux login and KWallet passwords are independent. Activation rejects account
password drift; [explicit rotation](admin-passwords.md#explicit-replacement-and-activation-safety)
requires user confirmation or password entry. Storage unlock does not transfer the
disk password to login or change the application's service identity.
Additional mappings use `luxnix-data-<mount-path>`, with `-member-N` for multiple
members. Duplicate names fail evaluation. Coordinate existing mapper/keyfile
renames before activation; never regenerate a key to repair a naming mismatch.

### gc-10 reconstruction and future mirroring

The boot-LUKS target has a separate system NVMe and a one-member MD RAID1
application array, then LUKS2 and Btrfs subvolumes for application, PostgreSQL
and backups. One member provides no redundancy. Future mirror addition requires
a reviewed MD growth operation, never rerunning Disko over live data.
The retained legacy layout cannot be converted by configuration activation.
Preserve complete data, PostgreSQL, original keys/salts and independent unlock
credentials before reprovisioning. The gc-10 export-disk and temporary plaintext
backup exceptions do not authorize plaintext production application storage;
see [cutover scope](#gc-10-cutover-scope-operator-decision-2026-11-03).

## Splash unlock and generation recovery

Plymouth uses the plain-text `details` theme. Root unlock waits without a time or
attempt limit. Ctrl+Alt+Del requests a persistent boot-menu choice for the next
restart; if writing the EFI variable fails, the normal menu timeout applies.
Retain a known-compatible generation, console access and independent SSH access.
Compare `/run/current-system`, `/run/booted-system`, the system profile and
bootloader default separately: failed activation can leave them different.
Pre-migration generations cannot boot a newly repartitioned layout; a generation
rollback does not reverse formatting or database migrations.

### Password setup during rebuild

On an already encrypted host, build the exact reviewed candidate and use its
helpers in a private interactive terminal (not a recorded/shared session):

```sh
sudo ./result/sw/bin/luxnix-setup-root-encryption --setup-password
sudo ./result/sw/bin/luxnix-verify-boot-storage
```

Replace `./result` with the actual candidate result. Retry normal boot staging
only after both checks pass. The first helper diagnoses the root and verifies
an existing disk password; it cannot provision plaintext root. A root-only pass
does not prove secondary-volume unlock or physical boot acceptance.
Use the candidate helper when the installed helper is outdated.

Verification stores a private host/UUID/header-bound receipt under
`/var/lib/luxnix-boot-passphrase`, never a password. Unchanged headers need no
repeat prompt. Explicit `sudo luxnix-setup-boot-password --change` adds a password
(at least 12 characters), requires an existing credential, backs up the header
and preserves old slots. Missing terminal or failed verification aborts activation.
Fresh installation sets the initial password at Disko's prompt. Rebuilds do not
rotate Linux or wallet passwords.

## Single production path and retained recovery

New installations require `root_encryption: luks2`. Use `fresh/new-disks` for
empty new disks, `disposable/discard-approved` only for approved disposable disks,
and `migration/old-disks` or `migration/whole-disk-image` when retaining data.
Preserve machine/application credentials even for disposable installations.
Retain legacy containers and decryptors until migration and recovery retention
are accepted. TPM/container/network-release/PAM enrollment is not a new-install
path. Existing raw-offset boot-key installations still require physical acceptance;
do not infer encryption or enrollment targets from command aliases.

## Guided operator workflow

Use the [quickstart](boot-storage-quickstart.md) and `devenv shell boot-storage-setup` for normal
operation. The task reads `autoconf/config.yml`; it does not require separate
`--spec` or `--state` arguments.

### Configuration and recovery media

- `paths.nix_output`: absolute path to the durable, reviewed, clean release checkout.
- `boot_storage.hosts.<host>`: hardware UUID, `root_encryption`, installation mode,
  retention and exact disk `path`, `serial`, `size_bytes`.
- `boot_storage.state_root`: independent recovery directory; the media helper uses
  `/recovery/luxnix-state` and stores each plan under its host name.
- `--current-host` selects the configured hostname or a unique hardware-UUID match.
  `--host`, `--config` and `--device` select explicit reviewed alternatives.

Media preparation selects an existing USB/removable ext4, XFS or Btrfs filesystem,
excludes system/target disks, checks at least 1 GiB free for metadata and mounts it
at `/recovery`. Multiple candidates require `--device`; blank, unsupported or
ambiguous media stop setup. Existing media is never formatted. This is journal
storage, not an application backup. Encryption is optional for non-secret evidence;
credentials and application backups keep their separate protection requirements.

Planning builds and pins the system closure and Disko executable, source revision,
lockfile, hardware and provisioner digest. Keep that release unchanged; never reset
a saved journal to accommodate a new checkout. Before installer boot, preserve the
checkout, built artifacts and evidence independently at their planned paths.
Installer state must be root-owned and private, outside `/mnt` and selected disks.
Use the reviewed root Python environment there; do not run `sudo devenv` on the
installed desktop. Trusted installer checks reject target-backed Nix stores,
active swap, mounted target disks and conflicting mappings.

### Evidence and advanced interface

`next` displays required checks; `review --assessor <name> --report <private-notes>`
asks for explicit confirmation of performed checks. Notes must be private,
nonempty and contain no secrets. The task pauses for missing notes, credentials,
installer boot or interrupted writes. It never invents evidence or reboots.

The lower-level `devenv shell boot-storage-migration` interface remains available for reviewed
automation: `plan --spec <private-spec.yml> --state <private-state-directory>`,
`status`, `attest`, `prepare-access`, `check` and `install`. A native spec has
`schema_version: 1`, `host`, `checkout`, `hardware_uuid`, `root_encryption`,
`installation`, `source_retention` and the disk fields above.

Stages are `recovery`, `backup`, `restore`, `prepared`, then physical `acceptance`.
Fresh/disposable plans omit backup/restore stages, not credential preservation.
Evidence JSON contains exactly `schema_version: 1`, `plan_id`, `stage`, `checks`
and a nonempty `artifacts` list of private absolute paths. Use the check names from
`status`; every result must be performed and true. Artifact hashes bind evidence
to the plan. Pre-install assessments expire after 24 hours and require reassessment.
Migration recovery requires exactly one fresh [readiness admission](#readiness-observations-versus-admission)
JSON artifact; the simple notes-only review does not replace this report.

From the trusted installer, `check --stage provision` verifies prerequisites
without formatting. The setup workflow separately confirms erasure and runs pinned
Disko. Restore/enroll credentials, then `prepare-access` prepares missing admin
hashes and optional initrd SSH identity while preserving existing credentials.
Record `prepared` evidence and pass `check --stage install` before the separate
install confirmation. Installation verifies mounts, disk identities, secondary
keys, admin hash and SSH configuration before and after the install-only command;
it does not test a live login. A machine-wide lock prevents concurrent installers.
Secure Boot must use the [supported signing workflow](secure-boot.md); unsupported
signed first-install combinations remain blocked.

### Interrupted setup

Run `next --host <host>` using the same state. A completed format is never
repeated. A running/interrupted provision blocks all automatic retries. Preserve
`provision.json`: it records disk metadata and execution state, **not a backup**.
Inspect the disks; repair/mount the intended complete layout from trusted media,
then preview and explicitly accept it without rerunning Disko:

```sh
python -m lx_administration.storage.boot_setup recover --host <host> --assessor <admin>
python -m lx_administration.storage.boot_setup recover --host <host> --assessor <admin> --apply
```

Recovery rechecks hardware, encrypted filesystems and evidence and requires an
exact terminal confirmation. Incomplete or mismatched layouts remain blocked;
restore retained disks/backups or arrange a separately reviewed reprovision.
For an interrupted installation, follow the existing `install-recovery`
assessment and `boot-storage-migration install --retry-interrupted` procedure.
Never delete journals to bypass a blocked retry. Old boot generations cannot
undo formatting or recover lost keys.

### Save and verify disk-password custody

After the installed host is reachable, use the controller's existing encrypted
vault and configured independent recovery envelopes. The custody selection must
already exist (`storage-recovery-custody prepare` in the installation guide).

```sh
devenv shell storage-provision setup --host <host> --volume cryptroot --apply
```

Add `--sudo-password-file <private-file>` if passwordless sudo is unavailable.
For retained containers replace `cryptroot` with `luxnix-secrets`, then repeat
for `luxnix-app-storage`. Omit `--apply` to preview. Setup tests a stored key or
asks privately for the current password, verifies both encrypted recovery copies,
then shows it once and asks for `SAVED`. Acknowledged keys are not shown again.
Wrong passwords or mismatched identities stop setup; no keys are removed.

### Remote SSH root unlock

Remote unlock is opt-in; no fleet host is enabled by this change. Configure
`luxnix.storage.operatorUnlocked.remoteUnlock` through the canonical host YAML
and regenerate normally. Set `enable`, the exact `interface`, required NIC
`kernelModules`, a static CIDR `address`, optional `gateway`, explicit management
`allowedSources` CIDRs and dedicated Ed25519 `authorizedKeys`. The default SSH
port is 2222. These keys grant only the interactive disk-unlock prompt; shell
commands, forwarding and inherited normal-login keys are disabled. Root waits
without a timeout or passphrase attempt limit in this mode, so an operator can
reconnect after a mistaken passphrase. Console unlock remains available.

`prepare-access` creates the dedicated host key once on encrypted target root
and prints its public key. Pin it in the operator's known_hosts through the
trusted installer channel before connecting. Then use SSH with strict host-key
checking and a terminal (`ssh -tt -p 2222 root@<configured-address>`), enter the
root disk credential, and reconnect to normal SSH after boot. Test this from the
actual management network before relying on unattended power restoration.

The dedicated SSH host private key is included in the unencrypted initrd. Never
reuse a normal host or login key for this purpose. Use a trusted management
network and protect the boot chain. The current controller-held Secure Boot
signing workflow rejects host-local initrd secrets, so combining it with this
remote-unlock mode is currently unsupported; do not disable that assertion or
silently downgrade Secure Boot. Hardware, firmware and network recovery still
need a physical acceptance test.

### Readiness observations versus admission

`devenv shell storage-readiness --limit <host>` prints a summary with admission
reasons. Full observations contain sensitive host facts and are suppressed from
Ansible output. Set `storage_readiness_save_report: true` in the private request
to retain the full JSON on the controller at
`cmdb/storage-readiness/<host>.json`. The directory and report must remain owned
by the controller user with private permissions; unsafe paths fail closed.
This local artifact is gitignored. Use that JSON file for migration evidence.
A successful observation only means the report was collected. For an
enforced baseline, pass a private YAML request with `-e @<private-request.yml>`:
`storage_readiness_mode: admit`, `storage_expected_host`,
`storage_expected_layout` (`legacy-containers`, `unencrypted-root` or `boot-luks`) and
`storage_expected_serials` (the exact list of all attached physical disk serials).
Admission requires one selected host and administrator access. Missing probes,
wrong identities, mismatched boot generations or active swap reject admission.
This intentionally conservative migration baseline requires no active swap,
even though normal runtime supports encrypted swap. It makes no swap changes.

Boot-LUKS admission calls the installed verifier, including read-only secondary
key tests. It may access protected keys but never prints their contents. Reports
include observation time, boot identity and a content hash; keep them private.
Admission is not proof of independent recovery, restore usability or permission
to erase disks. The prepared-target installer performs fresh machine checks.

## Before touching a production disk

This procedure requires an authorized operator at a working console, maintenance
window, trusted installer/recovery media, independent recovery custody, sufficient
new storage and a verified backup. Nothing here authorizes formatting in an
ordinary update. Prefer new disks so old disks remain recoverable. Do not attempt
in-place conversion or overwrite the only working LUKS header.

1. Record the host, inventory target, reviewed Git revision, flake.lock and exact
   serial-number disk IDs. When replacing disks, update the host disk identifiers
   to the verified new serials before building. Disconnect old disks before
   creating identically labeled partitions; duplicate GPT labels can select the
   wrong device. If disks must be reused, first retain verified full old-disk
   images including headers on independent encrypted storage. Run the documented
   connectivity check. Privately save
   `lsblk -o NAME,PATH,TYPE,FSTYPE,UUID,PARTUUID,MOUNTPOINTS`, `findmnt --real`,
   `swapon --show`, `cryptsetup status` for each mapping, and
   `btrfs filesystem show` for each Btrfs filesystem. Include bind ancestry,
   every RAID member, actual PostgreSQL data_directory, tablespaces/WAL links,
   backup locations and effective application runtime paths. Do not commit this
   sensitive inventory. Confirm gc-10 disk swap is disabled in the running system.
2. Inventory existing inner containers and their UUIDs, recovery slots and all
   secret destinations using the legacy inventory metadata. Record which bound
   directory owns each destination, including nested binds (for example hub PKI
   and retained salts). Back up LUKS headers privately to independent encrypted
   media and test the recovery credential without changing slots.
3. Stop ingress, processing/transfer workers, timers, application writers and
   database backup jobs. Produce a consistent PostgreSQL logical dump and globals
   with the matching version's tools, or a verified physical backup including WAL
   with PostgreSQL stopped. Record the PostgreSQL major version and extensions.
   Do not copy a live PGDATA directory as an ordinary file backup.
4. Back up the **mounted logical application paths**, including nested secret
   mounts, not just the container filenames or parent directory underneath them.
   Use an encrypted destination and preserve numeric ownership, permissions,
   ACLs, xattrs, symlinks and hard links (`rsync -aHAX --numeric-ids` after writers
   stop is suitable). Include `/etc/secrets`, existing account hashes,
   application master keys, all retained decryption keys/salts, hub identities,
   TLS/AppRole material, and SOPS private age identities. Include the SOPS
   ciphertext required by the built system. Do not generate replacement keys.
5. Restore the backup to an isolated encrypted test target. Validate PostgreSQL
   consistency/queries and decrypt representative old media with the restored
   keys, including data encrypted before rotations. Compare protected manifests
   and ownership. Retain the backup and old storage until production acceptance.

## Snapshot backups from the existing gc-09 and gc-10 installations

For these two hosts, `devenv shell storage-migration-snapshot` preserves the existing mounted
Btrfs subvolumes without changing their layouts. It briefly masks and stops
application/database writers, freezes mounted inner filesystems while snapshotting
their backing storage, then unfreezes and restores previously active services.
Inactive services remain inactive. Review free space first: retained snapshots
consume additional space as the original filesystems change. Keep the source
snapshots until independently verified restore acceptance; no automatic cleanup
or storage cutover is performed.

One host-wide lock serializes snapshot operations, including different snapshot
identifiers. A completed retry validates the original source and retained
read-only snapshots and returns unchanged. A partial run is retained and never
combined with a later snapshot window. Use the same wrapper and identifier with
`-e migration_snapshot_action=status` to inspect it. The host systemd supervisor runs journal recovery automatically after a crash,
SSH disconnect or runtime timeout, with bounded retries. It kills remaining
snapshot children before thawing and restarting services. OpenBao must actually
be initialized and unsealed before its dependent writers restart. If automatic
recovery remains unsuccessful, inspect status and explicitly select `-e migration_snapshot_action=recover` to restore
only the journaled writer and freeze state. Recovery refuses changed source
identities and leaves writers stopped if thawing fails. Then choose a new
snapshot identifier. Do not remove journals, snapshots or locks to force a retry.
Old journals created before this recovery protocol require manual review.
Recovery reconciles a journaled `pending_snapshot` before declaring success.
An existing target must be a read-only Btrfs snapshot at the recorded path with
the expected source parent UUID; its discovered identity is saved before reuse.
An absent target means creation did not complete. An invalid or uncertain target
keeps recovery blocked and writers gated for operator review, while thawing is
still attempted. No orphan is silently ignored or automatically deleted.

Run connectivity first, then the snapshot wrapper with an explicit host, unique
identifier and the existing private sudo-password file on encrypted controller
storage. Use `-e ansible_become_user=root`. Never send passwords through chat or
command arguments.

New backups use **dedicated native age identities**, separate from SSH login.
The operator selects private directories on encrypted controller storage and
independent encrypted custodian media, then runs:

```sh
devenv shell storage-recovery-custody prepare \
  --identity <controller-age-identity> \
  --custodian-identity <independent-age-identity>
```

The command creates only missing identities, refuses replacement, checks that
the two locations share no physical disk, and proves both identities can decrypt
a freshly encrypted challenge. A repeated `prepare` preserves existing valid
keys. `verify` with the same arguments repeats the storage and cryptographic
checks without generating keys. The custodian must also be able to unlock the
independent media without the original controller; a successful device probe
cannot establish that human recovery capability.

`devenv shell storage-migration-backup` accepts the host and snapshot identifier,
an exact existing backup mountpoint, `--identity <controller-age-identity>`,
`--custodian-identity <independent-age-identity>` and the private sudo-password
file. See `devenv/commands.yml` for the complete arguments. Both identity media
must be available for the automated verification. The wrapper reads only the
recorded read-only snapshots and encrypts compressed Btrfs streams to both public
recipients. The backup disk itself may be plaintext because only ciphertext is
written; neither private identity may be stored there unencrypted.

Each archive is fully decrypted and checked against its stream hash with **each**
identity before publication. `.partial` files are not accepted backups.
`receipt.json` binds components and custody to the complete source-plan digest
and recipient set. Reruns reject changed plans, snapshot identities or recipients
before replacing plan evidence or reusing components. Durable component metadata
allows independently authenticated recovery after interruption between archive
publication and receipt saving. Retain interrupted artifacts for verification;
never delete them simply to force a retry.
Controller reuse also requires the recorded producer code hash, source revision,
identity paths and stable custody selection to match, and every component must
carry the same plan binding. Fresh custody verification is saved separately from
the original receipt. A changed tool or checkout therefore requires review of
the retained backup; never edit provenance to bypass the check.
For an existing published archive without completion metadata, explicitly select
`--recover-existing`. The controller rereads the current read-only snapshot and
requires both identities to decrypt to that exact compressed stream hash before
adopting the archive. Host-local recovery combines `--recover-existing` with
`--verify <component>` and verifies each recorded recipient separately through
stdin. Supply both public recipients even during verification. Old receipts
without plan binding require operator review; they are never silently relabeled
as a backup of the current plan.
Changing recipients does not rewrite old archives: retain the previous identities
and backups, and use a new snapshot identifier for subsequent backups.

For gc-09's operator-selected local external disk,
`ansible/playbooks/storage-local-backup.yml` receives only two distinct public
native age recipients, `backup_recipient` and `backup_custodian_recipient`. It
verifies the exact mounted filesystem UUID and writes new root-private
directories without modifying existing files. The
`luxnix-local-migration-backup.service` job creates `.unverified` ciphertext;
these files are not accepted backups. For each component, run the standalone
archive tool's `--verify` operation once with each recorded identity supplied on
stdin. It keeps the identity in an anonymous RAM descriptor, rejects disk
swap/writeback and authenticates the whole archive. Only after both recipients
have passed does it publish the archive. Never save an identity on gc-09's
plaintext root. Verification and creation hold the same receipt lock.

Migration coverage and writer selection live in
`lx_administration/storage/migration-policy.yml`. Review that policy whenever
adding a host, protected mount or application writer. The coverage tests compare
the policy with declared storage consumers; a newly declared protected path must
be covered before taking a migration snapshot. Deploy the policy and its loader
beside standalone snapshot and archive tools from the same reviewed checkout.

These are **filesystem snapshots, not whole-disk images**: they cover root, home,
Nix, persist and logs, plus gc-10's data filesystem. They preserve existing inner
container files, including their headers. Unmounted unrelated subvolumes and
external export disks are outside that scope. Preserve EFI/partition metadata
and controller `.lxv` custody separately. Do not reuse source disks on the basis
of these archives alone; retain old disks or obtain the full-disk images required
above. PostgreSQL/media restore tests are still mandatory.

A supplementary host copy of a dedicated age identity can be made with the
operator-authorized `ansible/playbooks/storage-backup-identity-escrow.yml`, through
`scripts/run-secret-playbook.sh` and an explicit single-host `--limit`. Supply a
private variables file containing `recovery_expected_host`, `recovery_mount`,
`backup_custody_id`, `backup_identity_source` and `backup_identity_recipient`.
The recovery host must match the selected inventory host; the mount must already
be encrypted and mounted. The public recipient must match the native age identity.
The playbook preserves it at
`<recovery_mount>/storage-recovery/<backup_custody_id>/identity.agekey`, root-owned
0400, refuses a different existing file and verifies bytes and recipient after
copying. The operator chooses a custody scope that describes the backups it
protects; there is no implicit `gc-02` scope or default SSH private key. This
supplementary host copy does not replace independent offline custody.

**Existing SSH-encrypted backups remain recoverable with their original private
SSH identity.** The new workflow neither deletes that identity nor re-encrypts old
archives. Revoking its SSH login authorization does not invalidate decryption;
losing the private bytes does. Retain old encrypted identity copies until old
archives have passed independent restore and their retention is explicitly
ended. The host-local tool supports `--legacy-ssh-identity --verify <component>`
only for checking existing legacy archives. It does not create new SSH-encrypted
backups. Old copies already stored on gs-02 are not removed by the new playbook;
review their access and SSH authorization separately without discarding backup
recovery material.

On an isolated encrypted Btrfs restore target, decrypt each archive with
`age -d -i <the-corresponding-identity>`, decompress with `gzip -d`, and feed it to
`btrfs receive <restore-directory>` using a pipeline that checks every exit code.
Restore to an empty test directory, never over a production filesystem. Restore
legacy containers with their original recovery credentials; independent age
copies of those records can be prepared as described in
[Recovery credentials](legacy-storage-recovery.md#recovery-credentials).
Then restore their logical contents into the final encrypted layout. Archive
authentication proves transport and decryption, not database/media usability.

### Reusing the original NVMe

After restore tests pass, shut down normally and boot the trusted recovery stick.
Identify the original NVMe by its recorded serial, not its current `/dev/nvme*`
number. Keep every source partition unmounted and disable installer automounting
and disk swap. Mount only the independently identified backup disk. Stream the
**entire source device**, including GPT and EFI, through compression and age
encryption into a new exclusively created archive; check every pipeline exit
status and retain partial output on failure. Record the raw byte count and SHA256
while reading. Fully decrypt and decompress the archive to a second byte count
and hash, and require an exact match before treating it as recoverable. Never
write a plaintext image or recovery private identity onto the external disk.

Keep this image, the snapshot backups and their independent recovery identity
until restored PostgreSQL, old encrypted media and cold-boot acceptance pass.
Once the NVMe is formatted, rollback requires restoring its whole-disk image
from trusted recovery media; selecting an older NixOS generation cannot restore
the old partition layout or data. Preserve any new writes separately before
rolling back, since restoring the image discards them.

## Reprovision and restore (explicit destructive operator action)

### gc-10 cutover scope (operator decision, 2026-11-03)

The requested migration includes the live backend, not only a backup. Reuse the
two internal disks only after verified offline whole-disk images and a tested
restore. For this migration the operator selected **plaintext backup archives**
on the existing `Backup-24-11` filesystem, without an additional archive password.
This is a host-specific exception to the encrypted-archive procedure above;
do not run that procedure and describe its age ciphertext as plaintext. Raw disk
images still contain the original encrypted containers and need the existing
container credentials for recovery. Preserve those credentials until recovery
retention ends. Keep backup access private and existing backup contents intact.

Start by extracting the existing containers into a private plaintext file tree
on the selected backup disk. This copy can precede the offline disk work: keep
the original containers closed to writers, open separate read-only mappings,
and verify file contents and metadata after copying. Preserve the originals.
Do not interpret permission to copy data as permission to erase disks or remove
containers. A verified file copy is a restore source; it becomes the live backend
only after the separate path cutover and application checks below.

The installed backend remains `boot-luks`: one root unlock at boot, with the
secondary disk unlocked by its keyfile on encrypted root. Restore logical data
from inside the old containers, preserving numeric ownership, permissions,
ACLs, extended attributes, application keys and historical identity salts:

| Legacy container directory | Live destination after restore |
| --- | --- |
| `luxnix-app-storage/application` | `/var/lib/lx-annotate` (data-disk Btrfs subvolume) |
| `luxnix-app-storage/postgresql` | `/var/lib/postgresql` (data-disk Btrfs subvolume) |
| `luxnix-app-storage/postgresql-backups` | `/var/backup/postgresql` (data-disk Btrfs subvolume) |
| `luxnix-secrets/host-secrets` | `/etc/secrets` |
| `luxnix-secrets/managed-secrets` | `/etc/secrets/vault` |
| `luxnix-secrets/identity-salt-recovery` | `/var/lib/lx-annotate-identity-salts` |
| `luxnix-secrets/identity-salt-replica` | `/var/lib/lx-annotate/data/.identity-salt-recovery` |
| `luxnix-secrets/wheel-conf` | `/var/endoreg-service-user/lx-annotate-wheel/conf` |
| `luxnix-secrets/hub-client-pki` | `/var/lib/lx-annotate/hub-pki` |

Reconcile this table with the final evaluated bind metadata and actual source
contents before copying. Restore nested destinations after their parent tree.
Do not restore the `.luks` backing files or obsolete container mount directories
into the new live filesystem. Keep their complete originals in the recovery
images. Select `boot-luks`, disable local OpenBao enrollment tooling and leave
legacy container migration disabled in the installation release. Shared legacy
metadata stays available for other hosts and for detecting stale mounts.

Retirement is complete only after the installed mount graph points at the new
encrypted partitions, no legacy unlock units or container mounts remain active,
PostgreSQL checks and historical-media decryption pass, and a cold boot starts
the application after one storage prompt. The external backup is recovery
storage, never the application's live backend. Do not delete recovery images or
claim physical acceptance based on a configuration build.

### Installation procedure

1. Review the evaluated Disko layout for the exact host against serials and the
   recorded installed layout. Build the system on a durable reviewed checkout;
   a temporary verification checkout must never become the production source.
   Ensure trusted installation media can unlock the restored system and verify
   Secure Boot signatures where enabled. Record all mountpoints and crypttab
   entries from evaluation before any destructive command.
   Test the one-time USB boot menu from the local console before erasing storage.
   Possessing a recovery stick does not prove firmware permits booting it. If an
   unknown firmware password blocks recovery, retain the working installation;
   do not reset firmware or disable Secure Boot as a migration workaround.
2. On the authorized replacement disks only (or an explicitly approved reused
   disk after its offline whole-disk image has been verified), run the reviewed destructive Disko
   provisioning workflow to create the complete layout (EFI, LUKS2 root and all
   data members). Disko uses prompted recovery credentials at this stage, not
   runtime keyfiles. Verify all member mappings are open before Btrfs array
   creation. Mount the resulting target root at `/mnt` and its data filesystems
   at their declared paths beneath it. Test the recovery credentials before
   installing. Keep EFI free of private key material.
3. Generate each secondary key **once**, directly into private storage on the
   newly mounted encrypted root: `/mnt/etc/luks-keys/<crypttab-mapping>.key`,
   root-owned 0400, at least 32 random bytes, with parent root-owned 0700. Use
   exclusive creation and refuse an existing pathname. For already encrypted
   retained data disks, restore their enrolled keys instead. A missing existing
   key is a recovery failure, not permission to regenerate.
4. Enroll each new key with `cryptsetup luksAddKey` against its verified secondary
   device, supplying only the key **file path** as the new key and entering the
   existing recovery credential at the hidden prompt. Test that key with
   `cryptsetup open --test-passphrase --key-file <key-path> <verified-device>`.
   Retain and test independent recovery slots and encrypted external key backups.
   Disko's format phase never generates runtime keys. **Do not rerun destructive
   Disko or nixos-anywhere's disk phase after creating keys or restoring data.**
5. Restore logical destinations directly at their existing application paths,
   flattening obsolete container and bind layers. Restore nested mounts separately
   to their intended directory. Restore account hashes before first login and the
   existing SOPS age key at its configured path (generation remains disabled).
   Restore PostgreSQL consistently using the matching major version. Verify
   numeric service IDs and permissions before enabling any writers.
6. Before first installation, ensure the mounted target has its standard
   root-owned `/var/lib` directory, then initialize its machine identity
   with `systemd-machine-id-setup --root=/mnt` from the trusted installer. Do not
   replace an existing identity on a restored installation. A bare chroot may
   report `cryptsetup status` type `n/a` without udev metadata. Expose the trusted
   installer's `/run/udev` at `/mnt/run/udev` through a read-only bind mount for
   staging/installation, and remove that temporary mount during installer
   teardown. Never accept `n/a` as proof of LUKS2. With its required mounts and
   Nix store available, use `nixos-enter --root /mnt --
   <built-closure>/sw/bin/luxnix-setup-boot-password` in a private terminal to
   verify the existing disk password and stage its receipt. A missing
   `/etc/machine-id` blocks staging; do not manufacture a receipt or bypass the
   check. Then install the already built closure onto the prepared target using the local
   NixOS install-only workflow, after reviewing `findmnt -R /mnt` and confirming
   the target serials again:

   ```sh
   python -m lx_administration.storage.boot_migration install --state <private-state-directory>
   ```

   This must run from the trusted installer, not the running old host. It must
   not repartition or format. Account hashes and service secrets must already
   have been restored. When migrating existing sops-nix configuration, remove
   the obsolete `operatorStorageKey.volumeKeys` entries; preserve the private age
   identity, applicationSecrets, consumers and pinned ciphertext. Data unlock keys
   are now local root-owned keyfiles, independent of SOPS installation. Do not run the general `nixos-anywhere` command with its
   default disk phase against this prepared installation. From the installed
   target run `luxnix-verify-boot-storage`; it binds each secondary key to the raw
   device and open LUKS2 mapping and tests the enrolled key without changing
   slots or mappings. A wrong key on an already open mapping therefore blocks
   the normal pre-switch check. Runtime consumer guards use `--mounted-storage`
   to check current mounts and permissions without repeated key derivation;
   that option does not prove next-boot unlock. Inspect every mapping, `findmnt` and
   `swapon --show`. Inspect the built initrd and EFI to confirm that neither
   secondary key contents nor private age identities were embedded.

## Acceptance, recovery and rollback limits

For boot-luks, cold boot with networking disconnected. Enter one root credential, confirm data
mappings open without further prompts, SOPS installation succeeds locally where
used, and normal login/database/application services start. Check service status,
query the restored database and decrypt old media. Existing optional remote
integration jobs may report network failure; local storage must not depend on them.

On a disposable test copy, repeat with one data disk absent and with an invalid
secondary key. Confirm bounded failure and no database/application write under
an unmounted target. Restore the original key and disk; restart the failed units.
Record private key hashes before and after repeated activation, cold boots and a
normal signed system update/reboot. Never put private keys or their contents in
logs. Test independent recovery credentials from trusted media, restore the key
backup onto encrypted root, and verify data again. A service start/build alone
is not acceptance. Record physical results separately from repository tests.

Recovery begins by checking device identity, mount graph, logs and key custody.
Never format a missing mapping or replace an unreadable key. Use the independent
root recovery credential; secondary disks need either their enrolled keyfile or
independent recovery slot. Application backup restore additionally needs the
original application master key, retained historical keys/salts and, where used,
SOPS age identity. A root passphrase alone cannot decrypt application backups
whose separate application keys have been lost.

Keep old disks disconnected and recoverable until signed-off acceptance. Before
new writes, rollback can boot the old disks with their old generation and keys.
After accepting new writes, reverting disks loses those writes unless a separate
consistent reverse migration is performed. A Nix generation rollback cannot undo
a disk format, restore missing keys or reconcile diverged databases.

## Temporary compatibility and removal

gc-09 selects `boot-luks` but still needs reprovisioning from its plaintext root.
On 2026-11-04 the owner retained gc-10's existing partitions and restored its
explicit `legacy-containers` profile with Plymouth passphrase unlock. Its
automatic migration is disabled; normal rebuilds preserve the existing data.
For hosts selecting `boot-luks`, the boot-storage pre-switch check
rejects `switch` and `boot` onto a plaintext root, so a rebuild on the old disks
fails before the bootloader changes. Never bypass it with `NIXOS_NO_CHECK=1`.
Both remain unmigrated in repository acceptance; inspect the live
host before making any claim about its root storage. For gc-10, no recovery
console is available for its plaintext-root reprovision.
Its original encrypted application and secrets containers remain mandatory;
this exception does not authorize plaintext application startup or claim root
protection. Disk swap stays disabled. The bounded
`ansible/playbooks/storage-legacy-recovery.yml` workflow preserves the existing
checkout, creates a retained release worktree, compares its built closure to the
controller build, validates original container UUIDs and recovery credentials,
and uses the host-local `luxnix-safe-activate` worker without rebooting. A fresh
SSH connection must acknowledge completion before its watchdog expires. Automatic
rollback requires matching stateful compatibility manifests or an operator
assessment bound to the exact old/new closures and recovery evidence; it never
blindly rolls a database back across migrations. Run it through
`scripts/run-secret-playbook.sh` with an explicit gc-10 limit and private tmpfs
recovery variables; never put recovery passphrases in command arguments. Its
`--skip-tags activate` phase only prepares the release and opens authenticated
existing mappings. Verify the contained database and original application keys
before the separately selected activation phase. Select that phase by rerunning
the whole playbook without tag selection: every earlier step is repeated and
idempotent, and the playbook refuses `--tags activate` alone because it would
skip the target, closure and mapping gates. No missing container is created.

Remove the exception only after console-
assisted reprovision and verified restore; the final fleet architecture is unchanged.

`layout = "legacy-containers"` is an explicit maintenance/recovery exception for
an unmigrated host. Set it through the canonical host inventory, for example:

```yaml
host_luxnix:
  storage.operatorUnlocked.layout: '"legacy-containers"'
```

Run `devenv tasks run autoconf:check`, render/compare in an isolated directory,
then regenerate through `devenv tasks run autoconf:generate` under the documented
Autoconf workflow. Remove this explicit exception only as part of the verified
reprovision/restore procedure. The old `migration.enable` flag controls container
copying only; it is not proof of physical root migration and is ignored by the
boot-LUKS runtime. Compatibility retains the existing inventory container UUIDs, bind map,
SOPS container-key support and recovery tools. It is not a second final fleet
architecture and must not be used to claim root encryption. Current container
metadata remains solely to support this migration and prevent loss of recovery
information. Do not activate boot-luks on an old disk layout to try to convert it.

Retain container recovery for each unmigrated host until its physical acceptance
gates pass; see the [legacy host inventory](legacy-storage-recovery.md).
Remove legacy-only migration metadata and tests only after every fleet host has verified boot-LUKS acceptance and old storage has
reached its approved retention limit. No host is marked physically migrated by
this repository change. OpenBao identity provisioning and LX-Annotate encryption
remain independent; local OpenBao storage-unlock enrollment is superseded.

## Repository verification and physical evidence

The focused source/probe lane is:

```sh
python -m pytest -q tests/test_boot_storage.py tests/test_managed_secret_storage.py tests/test_operator_storage_migration.py
nix build .#checks.x86_64-linux.boot-storage --no-link -L
nix build .#checks.x86_64-linux.boot-storage-remote --no-link -L
nix build .#nixosConfigurations.gc-10.config.system.build.toplevel --no-link
nix build .#nixosConfigurations.gs-02.config.system.build.toplevel --no-link
devenv tasks run nix-quality:check
devenv tasks run docs:check
python scripts/lint_structure.py
```

The VM uses disposable root/data devices and synthetic credentials; it does not
exercise production hardware, application restore, production Secure Boot keys
or the fleet's Btrfs RAID hardware. Its Nix store is the test harness's shared
read-only store. A VM result cannot substitute for the physical acceptance steps
above. The fleet readiness tracker remains authoritative and must not be marked
complete from these repository checks alone.

## Coordinated hub snapshots

The scheduled gs-02 hub backup pauses the declared LX-Annotate/LX-Dtypes writer
services and timers. A systemd start condition prevents their automatic restart
throughout capture. Only after all writers stop cleanly does the coordinator
create a fresh PostgreSQL dump in root-controlled `/run`, copy protected media,
verify checksums and atomically publish the restore point. A failed or timed-out
writer prevents publication. This creates application downtime for the duration
of capture; size and schedule must be assessed before deployment.

The coordinator journals previously active units. Normal failure and systemd
`ExecStopPost` recovery remove the temporary dump and restart that saved set.
A failed restart leaves `/run/luxnix-hub-backup/recovery.json` for retry with the
installed `luxnix-hub-backup recover` command under the normal authorized host
maintenance workflow. Do not delete that journal to bypass recovery. Reboot
clears this runtime state and returns to declaratively configured startup.

Destinations must resolve physically beneath encrypted runtime storage, with no
symlink or traversal escape and no overlapping destination trees. Mandatory
rsync exclusions are derived from the actual destinations, including customized
locations. These checks do not replace backup encryption, retention or restore
acceptance. External/manual writers must also be quiesced; the unit set covers
declaratively configured application writers, not arbitrary operator processes.
A production restore and physical cold boot remain acceptance requirements.

The disposable integration check is `nix build
'.#checks.x86_64-linux.hub-backup' --no-link`. It exercises real PostgreSQL,
LUKS2-backed media, writer stop/start and a capacity failure, and verifies that
restored database references resolve within the captured media tree. It does
not establish a clinical production restore or inventory all manual writers.
