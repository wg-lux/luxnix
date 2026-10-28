# Encrypted storage and automatic startup

Encrypted storage is configured for every
host in `active_clients`. The `operator_unlocked_secrets` group has the same
membership, checked by tests. The reusable NixOS options live under
`luxnix.storage.operatorUnlocked`; inventory YAML owns each machine's layout.

## Normal startup

Start normally. Dependencies unlock existing volumes, mount the encrypted
directories, apply directory permissions and then start the database and
application. Startup never creates or formats a missing container. Migration is
an independent option and is disabled in the gc-10 pilot (ENC-25).

Every host, including gc-10, currently uses the default `unlockMethod =
"passphrase"`: an operator enters each container's passphrase at boot.
TPM-bound unlock is paused until root integrity (ENC-09) is solved, because
PCR 7 without Secure Boot and an integrity-protected root releases the key to
any boot. Before selecting `tpm2` again, each existing container must
first be enrolled on its own host, with a trusted signed boot chain and UEFI
Secure Boot enabled. In a private terminal, run once per configured mapping:

```bash
sudo luxnix-operator-storage enroll-tpm2 luxnix-secrets
sudo luxnix-operator-storage enroll-tpm2 luxnix-app-storage
```

The target profile replaces this legacy TPM token with host-local OpenBao:
`devenv shell openbao-local adopt` adds an OpenBao keyslot and removes every
`systemd-tpm2` token, so do not run `enroll-tpm2` on a host that is being
moved to `unlockMethod = "local-openbao"`. See
[local OpenBao enrollment](openbao-local.md#enrollment-and-volume-adoption).

Legacy enrollment adds a TPM slot bound to Secure Boot PCR 7 and preserves recovery
passphrases. Ordinary signed kernel updates do not bind enrollment to a specific
kernel measurement. Firmware trust changes may require recovery and reenrollment.
TPM startup uses only an enrolled TPM token, with no password or key-file fallback.
Missing containers, enrollment or Secure Boot prevent startup without formatting
data or waiting for a password. Normal application starts pull in the unlock and
mount dependencies automatically. Existing application media encryption is unchanged.
Filesystem permissions restrict service access; host root remains trusted.

This source configuration does not establish hardware enrollment. gc-10 was
observed with Secure Boot disabled; automatic TPM recovery has not been tested
there. Verify signed boot, both container credentials and recovery before rollout.
PCR 7 and signed boot alone do not establish integrity of arbitrary persistent
root/Nix-store code or enforce approved-version rollback. ENC-06/12 remain
unverified; this implementation is not a release of the strong acceptance profile.

### Boot with operator passphrase unlock

The shared `roles.endoreg-client` role requires encrypted operator storage and
operator-controlled unlock: either `unlockMethod = "passphrase"`, or
`unlockMethod = "local-openbao"` with the shared passphrase seal. The latter
requires [OpenBao enrollment and adoption](openbao-local.md#seal-selection-and-passphrase-operation)
and asks once to unseal OpenBao. Direct container passphrase unlock at boot
needs two separate credentials and no commands:

1. **Operator unlock.** During boot, the boot splash (or the console when no
   splash is configured) asks `Unlock luxnix-app-storage:` and then
   `Unlock luxnix-secrets:`. When both containers share a passphrase, the first
   answer is reused and the second prompt is skipped. The login screen stays
   hidden until the prompts are answered.
2. **Startup.** Each container opens, its mounts are checked as dm-crypt
   backed, and PostgreSQL, lx-annotate and its workers start on the decrypted
   storage.
3. **Laptop login.** The normal desktop login appears. The account password
   logs the user in; it never unlocks storage.

The prompt waits without a time limit. A wrong passphrase asks again, up to
five attempts per container; after that the unit fails and lx-annotate does
not start, so reboot to get a fresh prompt. SSH is available during the
prompt: for a remote reboot, an administrator can answer it with
`sudo systemd-tty-ask-password-agent`. Already open containers are reused
without a prompt, so a rebuild or switch never asks again. This sequence has
not yet been verified by a reboot on physical hardware.

For inspection or unlock only:

```bash
sudo luxnix-operator-storage status
sudo luxnix-operator-storage open
```

## Explicit provisioning and recovery custody

The admin workflow generates one random 256-bit recovery passphrase for each
new volume. It stores an authenticated Ansible Vault record under
`~/.lxv/storage-recovery/<machine-id>/<volume>.vault`, using the existing admin
vault key. The record binds host, machine ID, container path and native LUKS UUID.
An encrypted copy is published on the selected independent recovery host under
`~/.luxnix-recovery/<machine-id>/<luks-uuid>.vault`. The current gc-09 pilot uses
gs-01, designated by the operator as the dedicated recovery host outside both
gc-09 and gs-02. This designation does not establish a verified backup or restore.
Only ciphertext is sent to that host. Keep the admin vault key separately in
custodian recovery custody; it is not included with the export.

`devenv shell storage-provision provision --host gc-10 --volume luxnix-app-storage
--recovery-host gs-01` previews the exact target. `--apply` explicitly authorizes
the operation after both recovery copies are authenticated. It uses the deployed
`luxnix-storage-provision` helper, which requires Secure Boot and authenticated
recovery custody. The legacy `tpm2` backend enrolls a TPM token. Select
`--backend local-openbao` for a host with the local OpenBao tool installed and
its enrollment escrow confirmed. This deploy-time choice does not change its
boot unlock policy.

The local backend writes and reads back an independent UUID-bound OpenBao key
before allocation. It formats an unpublished private allocation with the
escrowed recovery passphrase, publishes only a valid authenticated LUKS header,
adds the OpenBao keyslot, and creates ext4 only for the authenticated new-volume
request. A retry resumes the same record, UUID and keyslots. A partial allocation
is private staging; an existing published container is never reformatted. The
mapping stays open for subsequent pre-copy. Boot never invokes this workflow.

For existing containers, use `storage-provision escrow` with the same host,
volume and recovery-host arguments plus `--existing-key-file <private-file>`.
The existing credential is tested before escrow; neither keyslots nor data are
changed. Both workflows accept `--sudo-password-file <private-file>` when sudo
authentication is required, and refuse unprotected credential files. Omit
`--apply` for inspection only. Copying authenticated ciphertext is not proof of
replacement-hardware recovery or completed ENC-16/17 acceptance.

For gc-09's existing containers, inspect each recovery plan with
`devenv shell storage-provision escrow --host gc-09 --volume luxnix-secrets --recovery-host gs-01`
and repeat with `--volume luxnix-app-storage`. The command may require the
documented private sudo-password file even for inspection because it reads the
LUKS UUID. Applying escrow requires the existing credential in protected storage
and operator authorization; it must not generate a replacement passphrase.
Keep deployment and reboot blocked until both credentials and independently
decryptable custody have been verified. Never put credentials in chat or arguments.

## Separately authorized migration

For each bind destination, migration checks encrypted backing storage and swap,
copies into private encrypted staging with rsync (permissions, ownership, ACLs,
xattrs and hard links), and verifies contents and metadata with checksums before
publishing it. Nested configured binds are migrated separately so a parent mount
does not hide their source data. An unconfigured nested filesystem requires an
explicit layout entry rather than being silently omitted.

A root-only receipt pins the destination path, inode and filesystem UUID.
Subsequent boots reuse that destination instead of copying stale originals back
over current application data. An interrupted staging copy resumes from its
matching private plan. A pre-existing populated destination is adopted only
when it already is the mounted source or when comparison proves equality.
Conflicting copies are never overwritten.

Receipt validation and adoption of an already mounted destination verify identity,
not historical content integrity. While an old LUKS mapping remains open, data
can be copied through its mounted filesystem into an independently encrypted
destination with a tested unlock credential. Keep the old mapping open until
recovery is proven. Stop all writers for the final copy and checksum/metadata
comparison, including PostgreSQL when copying its data directory. Handle nested
bind mounts separately. Require no differences, then verify database access,
authenticated application-media reads and recovery from the destination before
retiring the source. Never copy a live PostgreSQL data directory as a valid backup.

Normal boot migration refuses live writers. The explicit deployment path is:

```bash
devenv shell openbao-local rollout --limit <host-or-group> --recovery-host <host>
devenv shell openbao-local rollout --limit <host-or-group> --recovery-host <host> --apply
devenv shell openbao-local rollout --limit <host-or-group> --recovery-host <host> --apply --cutover
```

The first command plans only. Applied rollout enrolls local OpenBao, provisions
missing volumes with authenticated recovery exports, resumes incomplete new
volumes, and adopts existing volumes using their previously escrowed recovery
passphrases. It opens the mappings without changing the boot profile, then runs
`luxnix-storage-precopy.service`. Pre-copy leaves writers running and never
publishes a final destination or receipt.

`--cutover` additionally runs `luxnix-storage-cutover.service`: stop active
writers, synchronize and verify the final deltas, publish receipts, activate
binds, then start the previously active writers and configured `startupServices`.
Neither unit is started automatically at boot. Both require mounted encrypted
volumes. If final copying fails, newly published destinations return to private
staging and their new receipts are removed before writer recovery is attempted.
Recovery uses the normal service dependencies and never disables encrypted
storage checks. The original source directories are retained throughout.

`devenv tasks run tests:operator-storage-migration-vm` exercises the packaged
units with real LUKS, mounts, final-delta copying and reboot receipt reuse.

Account activation happens before application-volume unlock. The fleet policy
uses root-only boot-available files under `/var/lib/luxnix-account` for the admin
and enabled client account hashes. Activation copies each existing validated
hash once, preserves subsequent password rotations, and retains strict account
validation. These are the same one-way hashes needed by `/etc/shadow`, never
plaintext passwords, Vault keys or unlock passphrases.

Migration retains the original sources. **Plaintext originals and filesystem
snapshots are not erased by switching mounts.** Complete an approved cleanup and
retention procedure after verifying encrypted copies and independent recovery
backups. Until then, do not claim that all historical plaintext has disappeared.

## Layout and configuration

| Option | Contract |
| --- | --- |
| `enable` | Opt-in reusable module; enabled by the fleet inventory for active machines. |
| `unlockMethod` | `local-openbao` (target, after enrollment and adoption), or legacy `tpm2`/`passphrase`; independent of provisioning and migration. |
| `migration.enable` | Controls copying existing data only; false for the gc-10 pilot. Unlock services remain available when disabled. |
| `migration.accountHashes` | Boot-available hash destination to existing hash source; never generates account credentials. |
| `volumes` | Mapping device, mount point, filesystem, optional container path, minimum size, `noexec` and backing-filesystem dependencies. |
| `bindMounts` | Logical destination to volume name and relative preserved directory. |
| `guardedServices` | Existing executable service names to required mount points; nested mounts are included. |
| `startupServices` | Guarded consumers started by the helper; timer/manual-only jobs retain their schedules. |

Only newly created container files use automatic ext4 provisioning. Other
filesystems can use externally prepared mappings with `container = null`.
The fleet default preserves encrypted swap and GPT discovery. The previously
migrated gc-09, gc-10 and gs-02 hosts retain their explicit no-disk-swap policy
and RAM-only zram.
Hibernation is disabled for this manual-unlock lifecycle. The verifier rejects
unencrypted active swap and zram writeback before handling keys or copying data.

The shared layout protects `/etc/secrets` (including `.key` and `.psk`), managed
secrets, application directories, local PostgreSQL data and backup dumps, and
Vault server data where those services are enabled. It does not invent services
on machines that do not run them. Existing gs-02 storage paths and relative
subdirectories are retained by host YAML overrides.

| Host | Secrets container | Application container |
| --- | --- | --- |
| Default | `/var/lib/luxnix-secrets.luks` | `/var/lib/luxnix-app-storage.luks` |
| gc-10 | `/var/lib/luxnix-secrets.luks` | `/data/raid01/luxnix-app-storage.luks` |
| gs-02 | `/var/lib/luxnix-vault-tls.luks` | `/var/lib/luxnix-app-storage.luks` |

Backing filesystems such as gc-10's `/data/raid01` are started from declared
mount dependencies. Routine startup does not require manual root repartitioning,
directory creation or individual bind-mount commands.

## Application-side verification (lx-annotate)

When `enable` is true, the lx-annotate module renders
`LX_ANNOTATE_ENCRYPTED_VOLUME_PATHS` into the application environment. The
value is a JSON list of the mount points guarding `lx-annotate-runtime-env` and
`lx-annotate`: the secrets binds, identity-salt directories, wheel `conf`,
`/var/lib/lx-annotate` and a local `/var/lib/postgresql`. lx-annotate's
`verify_encrypted_storage` command runs in `lx-annotate-master-key-check` and in
`runtime_acceptance`. It then requires each path to be an active mount point
backed entirely by dm-crypt, and requires the data, storage and config roots and
the master key file to resolve into those mounts. Evaluation fails when
`runtime.encryptedDataDir` or `runtime.masterKeyFile` lies outside them.

Hosts with `enable = false` render no list. lx-annotate
then reports that no locations were declared and verifies only file-level
encryption. Enforcement starts only with an lx-annotate release that contains
this check. Older wheels ignore the variable, so rendering it is safe before the
wheel pin is updated.

## Deployment and verification

gc-10 uses the shared operator-unlocked storage workflow, including unlock
services and boot-available account hashes; migration is disabled. Its application
container remains on `/data/raid01`; the existing no-disk-swap policy is retained.
The temporary host-specific disable gate has been removed.

After each boot, follow [Boot with operator passphrase unlock](#boot-with-operator-passphrase-unlock)
to unlock the volumes and start the configured consumers. Retain offline recovery
passphrases; do not store unlock keys on plaintext root storage.

Before first activation, verify recovery credentials and independent backups,
keep existing secret hash sources readable for account activation, and schedule
the stopped-writer transition described above. Review and replace conflicting
`/etc/systemd/system.control` overrides before relying on generated mount units.
Removing the gate does not itself migrate live data or verify reboot recovery.

Regenerate through Autoconf and build from the reviewed durable checkout using
the [deployment workflow](deployment-guide.md). Review legacy overrides under
`/etc/systemd/system.control`: they take precedence over generated units. Retire
only overrides replaced by the reviewed configuration while writers are stopped.
Do not remove unrelated overrides or reformat populated containers.

Inspect `luxnix-storage-unlock-*.service`, `luxnix-storage-migrate.service` and
`luxnix-storage-check-*.service` for startup failures. Check `findmnt` sources,
Vault enrollment, PostgreSQL and HTTPS with the
[application diagnostics](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/services/lx-annotate-local/Diagnostics.md).
Never display passphrases, generated environments or private key contents.

Source tests and local builds do not prove a real reboot or backup restore.
The fleet automation has not been activated remotely. Historical gc-09/gc-10
live checks from October 23 verified their interim encrypted mounts and running
applications; they are not acceptance evidence for this new startup migration.

The helper also supports `header-backup <mapping> <destination-file>`. The target
must be new and on independent persistent encrypted recovery storage. Header
backups retain the keyslots present at creation, including later-removed
passphrases; replace them after keyslot changes and keep them in recovery custody.
