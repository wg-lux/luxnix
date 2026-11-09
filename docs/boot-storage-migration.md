# Boot LUKS storage: migration and recovery

For installation commands, use the [operator checklist](boot-storage-quickstart.md).
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
- A rebuild cannot encrypt plaintext root. Boot staging does not check the running
  storage layout or prompt for a disk password. A staged encrypted-root generation
  cannot boot until conversion finishes; retain a working recovery boot path.
  No boot unit formats disks or generates keys.
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
credentials before conversion. The current in-place tool rejects this multi-disk
layout; retain the working installation until support is implemented and tested.
The gc-10 backup exceptions do not authorize erasing its disks.

## Splash unlock and generation recovery

Plymouth uses the plain-text `details` theme. Root unlock waits without a time or
attempt limit. Ctrl+Alt+Del requests a persistent boot-menu choice for the next
restart; if writing the EFI variable fails, the normal menu timeout applies.
Retain a known-compatible generation, console access and independent SSH access.
Compare `/run/current-system`, `/run/booted-system`, the system profile and
bootloader default separately: failed activation can leave them different.
Generations from before the conversion cannot open the encrypted root, and a
generation rollback does not reverse the encryption or database migrations.

### Explicit password verification

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
and preserves old slots. Missing terminal or failed verification stops the helper.
Rebuilds do not invoke these helpers automatically; service storage guards still
reject missing or unencrypted storage.
In-place conversion sets the initial password at its own prompt. Rebuilds do not
rotate Linux or wallet passwords.

## Single production path and retained recovery

Setup requires `root_encryption: luks2`, `installation: in-place` and
`source_retention: in-place`; see [retired paths](#retired-destructive-installation-paths).
Retain legacy containers and decryptors until migration and recovery retention
are accepted. TPM/container/network-release/PAM enrollment is not a new-install
path. Existing raw-offset boot-key installations still require physical acceptance;
do not infer encryption or enrollment targets from command aliases.

## Guided operator workflow

Use the [quickstart](boot-storage-quickstart.md) and `devenv shell boot-storage-setup` for normal
operation. With no action it guides this machine's host and resumes the next step, and it
reads `autoconf/config.yml`, so it does not need `--spec` or `--state` arguments. Every
action defaults to this host; `--host` selects a reviewed alternative.

### Configuration and recovery media

- `paths.nix_output`: absolute path to the durable, reviewed, clean release checkout.
- `boot_storage.hosts.<host>`: hardware UUID, `root_encryption`, installation mode,
  retention and exact disk `path`, `serial`, `size_bytes`.
- `boot_storage.state_root`: independent recovery directory; the media helper uses
  `/recovery/luxnix-state` and stores each plan under its host name.
- Every action selects the configured hostname or a unique hardware-UUID match by
  default. `--host`, `--config` and `--device` select explicit reviewed alternatives.

Media preparation selects an existing USB/removable ext4, XFS or Btrfs filesystem,
excludes system/target disks, checks at least 1 GiB free for metadata and mounts it
at `/recovery`. Multiple candidates require `--device`; blank, unsupported or
ambiguous media stop setup. Existing media is never formatted. This is journal
storage, not an application backup. Encryption is optional for non-secret evidence;
credentials and application backups keep their separate protection requirements.

Planning builds and pins the system closure, source revision, lockfile and hardware.
Keep that release unchanged; never reset a saved journal to accommodate a new
checkout. [Replace the plan](#replacing-a-saved-plan) instead. Before installer boot, preserve the
checkout, built artifacts and evidence independently at their planned paths.
Installer state must be root-owned and private, outside `/mnt` and selected disks.
Use the reviewed root Python environment there; do not run `sudo devenv` on the
installed desktop. Trusted installer checks reject target-backed Nix stores,
active swap, mounted target disks and conflicting mappings.

### Replacing a saved plan

A saved plan cannot change. Setup stops if Autoconf differs from it, and preflight and
later steps stop if the checkout's revision or lockfile changed. Restore what changed,
or replace a plan that has not started. `devenv shell boot-storage-setup` checks this and
offers the replacement itself after you type `REPLACE PLAN <host>`, keeping the old state.
To do it by hand, first check its state, using the real host:

```sh
sudo ls -la /recovery/luxnix-state/gc-09
sudo jq '.spec | {installation, source_retention, checkout}' /recovery/luxnix-state/gc-09/plan.json
sudo jq .install.status /recovery/luxnix-state/gc-09/progress.json
sudo jq .phase /recovery/luxnix-state/gc-09/provision.json
```

A plan has not started when the install status is `pending` and the phase is `planned`
or `provision.json` does not exist. Any other result means work began: stop and follow
[interrupted setup](#interrupted-setup). Otherwise commit the changes so the checkout is
clean, move the old state aside without deleting it, and create the new plan:

```sh
sudo mv /recovery/luxnix-state/gc-09 /recovery/luxnix-state/gc-09.superseded-YYYY-MM-DD
devenv shell boot-storage-setup
```

Old reviews and receipts do not carry over, so repeat preflight and the recovery checks.

### In-place root encryption

`installation: in-place` with `source_retention: in-place` is the path for hosts with
data. It supports one plaintext Btrfs root partition; planning refuses other root
filesystems, MD arrays and additional encrypted partitions. From trusted installer
media, `advance --apply` asks for typed approval and the passphrases, then:

1. Tests every container passphrase and checks that the container data fits on root.
   A failure here leaves the disk untouched.
2. Shrinks Btrfs by 32 MiB for the header and runs `cryptsetup reencrypt --encrypt`.
3. Opens the result and confirms the filesystem UUID and `btrfs check`.
4. Erases the old plaintext swap partition, which holds no durable data. If it cannot
   check or erase it, the conversion continues and prints the command to finish by hand.
5. Opens each container read-only, copies each configured directory to its normal
   path, compares it with `diff -r`, then publishes it. Anything the old root held at
   that path moves to `<path>.pre-consolidation`.
6. Records the boot-passphrase receipt. `prepare-access` and `install` follow as usual.

If this stops, rerun the same command. It runs `cryptsetup repair` and resumes from
the LUKS2 header; never format or restart. Consolidated directories are not copied
again.

The root passphrase may contain only letters a-x, digits and spaces, because the boot
prompt can use a different keyboard layout than a desktop terminal. Older boot menu
entries cannot open the encrypted root. `cryptsetup` is available on the installed
system and in the initrd.

After conversion nothing opens the containers at boot; applications run directly on
the encrypted root. The container files stay untouched as a fallback until physical
acceptance is recorded. Then, on the installed system (it asks for `sudo` itself):

```bash
devenv shell boot-storage-setup retire-containers
devenv shell boot-storage-setup retire-containers --apply
```

This deletes only the container files, after typed approval, and refuses if a target
was not consolidated or a container is still attached. Their recovery records in the
admin vault are not changed. This path does not cover gc-10, whose containers are
on `/data/raid01` and whose layout is `legacy-containers`.

`nix build .#checks.x86_64-linux.boot-storage-in-place` runs this on a disposable VM
disk, with a power cut during encryption, cold boots and container retirement.

### Vault recovery before root encryption

In-place encryption requires `vault_recovery_tested` before provisioning.
The setup command does not back up Vault. An existing assessment without this check
is insufficient. If checks or source change, [replace the plan](#replacing-a-saved-plan);
never edit its recorded revision or mark an unperformed check complete.

Use [credential backup](credential-backup.md) to preserve the evaluated credential
files, including both admin/client boot hashes and their Vault sources, in an
authenticated encrypted archive. Run its verification after reboot or credential
changes and immediately before migration. It does not change passwords, replace
the full data backup, or complete the following recovery checks automatically. Its
archive also does not satisfy preflight, which compares plain copies in custody.

#### Secret preflight

Run this on the host being converted, after creating its plan and before review:

```bash
devenv shell boot-storage-setup preflight \
  --custody /run/luxnix-custody/custody [--vault-key-custody /path/to/key-copy] [--accept-absent <id>]
```

`--custody` takes a directory, never a device or disk. The guided command runs this for
you; run it directly to use `--vault-key-custody` or `--accept-absent`.

It works out what this host needs from the plan's evaluated configuration, tests
it, and writes `secret-preflight.json` to the plan state. `review` refuses to start
without a receipt less than 24 hours old for this exact plan, and `attest` and
provisioning reject an assessment that lacks it. A failed rerun removes the old
receipt. Preflight never copies or changes a credential; it prints the command for
anything missing, so expect the first run to stop and list what to copy. The guided
command copies only what is missing, after you agree, and never replaces an existing copy.

##### Preparing custody

Custody must be a private directory (mode 0700) owned by the operator on encrypted
storage outside the selected disks. A LUKS USB drive works, and so does a LUKS file on
the recovery drive, which is checked against the disk holding that file. The guided
command opens or creates that file for you; pass `--custody <directory>` to use an
already mounted location instead. The commands below are the manual equivalent.

**Create it only once.** `luksFormat` on an existing file destroys everything in it
without an error, even while it is mounted, and the mounted volume keeps working until
it closes. Check first; if this prints `Already exists`, go to the reopen commands:

```sh
sudo cryptsetup isLuks /recovery/luxnix-custody.luks && echo 'Already exists: do not recreate it'
```

To create the file on an existing recovery filesystem:

```sh
sudo truncate -s 2G /recovery/luxnix-custody.luks
sudo cryptsetup luksFormat --type luks2 /recovery/luxnix-custody.luks
sudo cryptsetup open /recovery/luxnix-custody.luks luxnix-custody
sudo mkfs.ext4 -q /dev/mapper/luxnix-custody
sudo mkdir -p /run/luxnix-custody
sudo mount -o nosuid,nodev,noexec /dev/mapper/luxnix-custody /run/luxnix-custody
sudo install -d -m 0700 -o "$USER" -g "$(id -gn)" /run/luxnix-custody/custody
```

Keep its passphrase outside the host being converted; losing it loses everything in
custody. `/run` is cleared at reboot, so reopen custody after each one, and use the same
commands to prove the copies are really stored after making them:

```sh
sudo cryptsetup open /recovery/luxnix-custody.luks luxnix-custody
sudo mkdir -p /run/luxnix-custody
sudo mount -o nosuid,nodev,noexec /dev/mapper/luxnix-custody /run/luxnix-custody
```

Skip this if it is already open: `findmnt /run/luxnix-custody` prints a line. Mounting
twice stacks mounts. Unmount it before reopening or removing the drive:

```sh
sudo umount /run/luxnix-custody
sudo cryptsetup close luxnix-custody
```

After copying the secrets, close custody, reopen it and rerun preflight. A pass from an
open volume alone does not prove the file can be opened again.

The custody, plan and any backup on one drive survive a system disk failure, not the
loss of that drive. If this host holds the admin vault, `--vault-key-custody` must be on
a different physical disk from custody, so a file on the same recovery drive is refused.

##### What preflight requires

| Required when | Items | Checked by |
| --- | --- | --- |
| Always | Admin password hash | Custody copy matches, format is valid and not retired, and you type the password that matches it |
| Client user enabled | Client password hash | Custody copy matches, format is valid and not retired |
| LX-Annotate enabled | Master key and any master keyring, identity keyring, every salt generation on the host or named by the keyring, salt recovery copies, Django secret key | Custody copy matches |
| Managed encrypted data enabled | Its LUKS key and UUID files | Custody copy matches |
| Hub receiver or storage node | Current and retiring recipient private keys | Custody copy matches |
| OpenVPN configured | Client key and certificate, TLS auth key, CA | Custody copy matches |
| SOPS secrets declared | Host age key or SSH identity | Custody copy matches |
| Encrypted volume outside the selected disks | Its key file | Custody copy matches |
| Admin vault on this host | `~/.lxv`, and `~/.lxv.key` through `--vault-key-custody` | Copies match, the key copy is on a separate disk, and it decrypts every record in the vault copy |

Copies go under `<custody>/<host>/secrets/<original-path>`, and the admin vault under
`<custody>/controller/.lxv`. Material that managed-secrets regenerates, enrollment
re-delivers or the admin vault re-exports is deliberately not required. Those
replacements assume a reachable VPN, Vault and controller, which is why their
prerequisites above are required.

Salts are issued by the host, or by Vault for an allowlisted center, and center
enrollment adds generations at runtime, so preflight also discovers them on the host
instead of relying on configuration alone.

A locked container looks like a missing file, so an absent item stops preflight.
Unlock it first. Keys that open or identify existing data cannot be waived on a plan
that keeps data, because provisioning would issue a replacement that
cannot read what exists: restore the original instead. Other items that truly never
existed on this host can be stated with `--accept-absent <id>`; the receipt records
that. Salts are the exception: one absent from both the host and custody is recorded as
`salt-regenerated`, and [the host creates a new one](center-identity-salt-activation.md#how-a-host-gets-its-salt).
Account hashes still need a valid custody copy. For a host with data use
`installation: in-place`; preflight warns on a mode that does not keep data. Hosts
running the Vault or OpenBao server stop here: preflight cannot verify their data and unseal material, so use
[Vault Server Rebuild](vault-server-rebuild.md).

Preflight proves that the keys exist, match and decrypt, not that the data can be
restored; your tested backup covers that. It also does not
prove the root LUKS passphrase, which is set during installation and tested at
physical acceptance. The remaining `vault_recovery_tested` confirmation still covers
anything outside this table.

#### What each store contains

`modules/nixos/luxnix/vault` defines several distinct credential locations:

- Host files: `luxnix.vault.dir`, `adminPasswordFile`,
  `adminPasswordHashedFile`, `key` and `psk`. Inspect evaluated paths for the
  selected host; these declarations do not copy secrets into the Nix closure.
- Controller Ansible Vault: normally `~/.lxv` and its independent unlocking key,
  normally `~/.lxv.key`. Both must survive if that controller disk is erased.
  Follow [local Vault recovery](vault-setup.md); do not initialize a replacement
  vault or generate new credentials as a migration shortcut.
- HashiCorp Vault: client token/AppRole files and any configured environment file
  provide access to a separate server. Preserve or test supported re-enrollment
  independently of the selected disk. If the selected machine hosts the server,
  preserve and test recovery of its Raft data and independent unseal/recovery
  material using [Vault Server Rebuild](vault-server-rebuild.md).

Before confirming this check, identify which stores actually apply, preserve
their required files in independent protected storage, and demonstrate recovery
without reading the original disk's credential files. Verify the recovered
administrator password/hash pair privately and retain application master keys,
historical keys and identity salts. Write only locations and test results in the
notes, never passwords, hashes, private keys or decrypted vault contents. The
unencrypted recovery journal filesystem alone is not suitable for plaintext
secrets. A backup containing a LUKS container still needs its original unlock key.

The installer validates a supplied administrator hash and preserves an existing
restored hash; it cannot infer that a different valid hash matches your previous
password. Restore the original hash to keep the same login password, and test
login after installation. Root LUKS uses a separate password. Re-enrollment of
Vault access must not replace keys needed to decrypt historical application data.

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

In-place stages are `recovery`, `prepared`, then physical `acceptance`.
Recovery includes an explicitly tested backup; the tool does not create it.
Evidence JSON contains exactly `schema_version: 1`, `plan_id`, `stage`, `checks`
and a nonempty `artifacts` list of private absolute paths. Use the check names from
`status`; every result must be performed and true. Artifact hashes bind evidence
to the plan. Pre-install assessments expire after 24 hours and require reassessment.

From the trusted installer, `check --stage provision` verifies prerequisites
without formatting. The setup workflow separately confirms in-place LUKS2 conversion. Restore/enroll credentials, then `prepare-access` prepares missing admin
hashes and optional initrd SSH identity while preserving existing credentials.
Record `prepared` evidence and pass `check --stage install` before the separate
install confirmation. Installation verifies mounts, disk identities, secondary
keys, admin hash and SSH configuration before and after the install-only command;
it does not test a live login. A machine-wide lock prevents concurrent installers.
Secure Boot must use the [supported signing workflow](secure-boot.md); unsupported
signed first-install combinations remain blocked.

### Interrupted setup

Run `devenv shell boot-storage-setup next`. A completed conversion is never
repeated. Interrupted in-place encryption resumes from its LUKS2 header. Preserve
`provision.json`: it records disk metadata and execution state, **not a backup**.
Inspect the disks; repair/mount the intended complete layout from trusted media,
then preview and explicitly accept it:

```sh
python -m lx_administration.storage.boot_setup recover --assessor <admin>
python -m lx_administration.storage.boot_setup recover --assessor <admin> --apply
```

Recovery rechecks hardware, encrypted filesystems and evidence and requires an
exact terminal confirmation. Incomplete or mismatched layouts remain blocked;
restore retained disks/backups or arrange a separately reviewed reprovision.
For an interrupted installation, follow the existing `install-recovery`
assessment and `boot-storage-migration install --retry-interrupted` procedure.
Never delete journals to bypass a blocked retry. Old boot generations cannot
open the encrypted root or recover lost keys.

### Save and verify disk-password custody

Do this only after the conversion, from the controller rather than the host itself,
once the installed host is reachable by SSH. Use the controller's existing encrypted
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
window, trusted installer/recovery media, independent recovery custody and a verified
backup. Nothing here authorizes formatting in an ordinary update. Never overwrite the
only working LUKS header. These steps are how to make and test that backup.

1. Record the host, inventory target, reviewed Git revision, flake.lock and exact
   serial-number disk IDs. Run the documented connectivity check. Privately save
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
   and ownership. Retain the backup until production acceptance.

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
and controller `.lxv` custody separately, or take a
[full-disk image](#full-disk-image-of-the-original-nvme). PostgreSQL/media restore
tests are still mandatory.

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

### Full-disk image of the original NVMe

To keep a complete copy before conversion, after restore tests pass, shut down normally and boot the trusted recovery stick.
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
This is recovery evidence, not permission to format the NVMe. In-place conversion
keeps its filesystem; restoration is a separately reviewed recovery action that
can replace newer writes. Preserve those writes before any recovery decision.

## Retired destructive installation paths

The Disko execution branch, fresh/disposable/erase-and-restore setup modes and
standalone wipe-and-reinstall template have been removed. Old plans remain
readable recovery evidence but cannot authorize setup, access preparation or
installation. Preserve them; never edit a saved plan to bypass rejection.

Use the [in-place workflow](#in-place-root-encryption) for supported existing
Btrfs roots. Unsupported arrays, extra encrypted devices and signed-install
combinations stop for review; there is no repartitioning fallback. Disko layout
declarations remain descriptive inputs for the expected mount graph, not a
command for converting an installed machine. Historical approval to erase a
host does not select a supported mode in this workflow.

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

In-place conversion leaves no old disk to return to, so the tested backup is the
rollback. Restoring it loses later writes unless they are preserved first. Retain it
and the container files until signed-off acceptance. A Nix generation rollback cannot
undo the encryption, restore missing keys or reconcile diverged databases.

## Temporary compatibility and removal

gc-09 selects `boot-luks` but still needs in-place conversion of its plaintext root.
On 2026-11-04 the owner retained gc-10's existing partitions and restored its
explicit `legacy-containers` profile with Plymouth passphrase unlock. Its
automatic migration is disabled; normal rebuilds preserve the existing data.
For hosts selecting `boot-luks`, rebuilds can stage the future encrypted-root
configuration while root is still plaintext. Staging does not perform conversion
or establish bootability. Boot recovery and complete conversion before selecting
that generation; activating it early can stop protected services.
Both remain unmigrated in repository acceptance; inspect the live
host before making any claim about its root storage. For gc-10, no recovery
console is available for converting its plaintext root.
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

Remove the exception only after a supported in-place conversion and verified
physical acceptance; unsupported layouts remain on their working installation.

`layout = "legacy-containers"` is an explicit maintenance/recovery exception for
an unmigrated host. Set it through the canonical host inventory, for example:

```yaml
host_luxnix:
  storage.operatorUnlocked.layout: '"legacy-containers"'
```

Run `devenv tasks run autoconf:check`, render/compare in an isolated directory,
then regenerate through `devenv tasks run autoconf:generate` under the documented
Autoconf workflow. Remove this explicit exception only as part of the verified
in-place conversion procedure. The old `migration.enable` flag controls container
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
python -m pytest -q tests/test_boot_storage.py tests/test_managed_secret_storage.py tests/test_operator_storage_migration.py tests/test_in_place.py tests/test_secret_preflight.py tests/test_recovery_custody.py tests/test_boot_guide.py
nix build .#checks.x86_64-linux.boot-storage --no-link -L
nix build .#checks.x86_64-linux.boot-storage-in-place --no-link -L
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

### In-place-only workflow retirement verification (2026-11-06)

The formatting executor and its Disko build input were removed from
`boot_setup.py` and `boot_migration.py`. Autoconf and the observation CLI accept
only in-place plans. Historical destructive plans remain readable evidence but
cannot pass planning or execution admission. The wipe/reinstall template and
`deploy-new-host` command entry were removed; command catalogs and operator guides
now point to the in-place preview.

```bash
.devenv/state/venv/bin/python -m pytest -q tests/test_boot_setup.py tests/test_boot_migration.py tests/test_in_place.py tests/test_secret_preflight.py tests/test_credential_backup.py tests/test_devenv_command_catalog.py tests/test_autoconf_cli.py tests/test_documentation_contract.py tests/test_project_map_contract.py --tb=short
.devenv/state/venv/bin/python -m pytest -q tests/test_boot_storage.py -k 'root_setup or setup_root' --tb=short
nix eval --raw '.#nixosConfigurations.gc-02.config.system.build.toplevel.drvPath'
python scripts/lint_structure.py
```

The main suite passed 279 tests; six root-diagnostic tests passed. gc-02 system
evaluation and all 23 structure
manifests passed. The Devenv documentation/Nix-quality wrappers stop at the
Secretspec reason policy, so their underlying checks were run directly.
Direct Nix quality passes parsing, Deadnix, Statix, formatting and flake-checker;
source visibility remains blocked by the unrelated untracked in-place VM test.
Python quality reports 71 existing diagnostics outside this change. No quality
baseline was raised. Changed-file whitespace checks pass; the repository-wide
check flags an unrelated trailing blank line in gc-09 inventory. Tracker
validation passes; the environment lifecycle readiness check remains 2/10.
No production disk operation, activation, full system build or VM boot was run.
These checks establish rejection of retired commands, not physical conversion
or boot acceptance on the fleet.

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
