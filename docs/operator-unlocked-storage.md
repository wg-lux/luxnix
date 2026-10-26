# Operator-passphrase storage and startup migration

Encrypted storage with automatic startup migration is the default for every
host in `active_clients`. The `operator_unlocked_secrets` group has the same
membership, checked by tests. The reusable NixOS options live under
`luxnix.storage.operatorUnlocked`; inventory YAML owns each machine's layout.

## Normal startup

Start normally. Dependencies unlock the volumes, copy and verify existing data
when needed, mount the encrypted directories, apply directory permissions and
then start the database and application. Plaintext data is migrated, not merely
rejected by a storage check. Services cannot write while their initial copy is
in progress.

Passphrases remain operator-held. Boot prompts use `systemd-ask-password`; for
remote administration use an interactive SSH terminal and:

```bash
sudo luxnix-operator-storage start
```

The helper provides a private terminal password agent and starts configured
boot-time consumers. It uses `start`, not `restart`. Already open containers and
already migrated data are reused; healthy services are not restarted. Locked
storage still needs its passphrase—unattended unlock is intentionally not enabled.

For inspection or unlock only:

```bash
sudo luxnix-operator-storage status
sudo luxnix-operator-storage open
```

## First startup and migration

For a missing configured container file, startup estimates source data size,
reserves space with headroom, asks for a new passphrase twice, exclusively
creates the file, initializes LUKS2 and ext4, and unlocks it. It never formats an
existing file, root partition or data partition. Existing containers are never
resized automatically. An interrupted initial format requires inspection rather
than an automatic reformat.

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

Migration does not stop a running database or copy its live files. For an
initial live retrofit, schedule a maintenance stop of writers; subsequent normal
boots order migration before those writers automatically. An actual problem
(insufficient space, wrong passphrase, conflicting data or an unconfigured
filesystem) prevents an unsafe cutover and retains the sources. No empty-data or
plaintext fallback is used.

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
| `migration.enable` | Defaults to true; provision/unlock and verify startup copies. Disable only for a separately prepared layout. |
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

Hosts with `enable = false`, including gated gc-10, render no list. lx-annotate
then reports that no locations were declared and verifies only file-level
encryption. Enforcement starts only with an lx-annotate release that contains
this check. Older wheels ignore the variable, so rendering it is safe before the
wheel pin is updated.

## Deployment and verification

gc-10 is temporarily gated out through its host YAML: both
`storage.operatorUnlocked.enable` and `migration.enable` are false, and account
hashes retain their existing Vault-backed paths. This permits a live deployment
without introducing the new mount, migration, unlock or account-copy workflow.
Keep gc-10's existing `/etc/systemd/system.control` mounts and storage guards;
they remain responsible for its encrypted application and database mounts.
Deploy only while both existing volumes are open and the account hashes are
readable. This gate does not establish reboot recovery: none of the tested
Desktop token files unlocked the application container on October 26.
Before removing the gate, establish a tested unlock credential and recovery
backup, then perform the stopped-writer migration and override review below.
The outer secrets directory and PostgreSQL backups remain unmigrated while gated.

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
