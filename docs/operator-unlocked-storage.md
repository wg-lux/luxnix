> Storage layout update: [Boot LUKS migration](boot-storage-migration.md) is the
> current fleet design. Container unlock, login unlock and local OpenBao storage
> enrollment below apply only to explicit `legacy-containers` recovery mode.
> Existing identity provisioning remains independent.

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

The repository selects `unlockMethod = "passphrase"` for the fleet, including
gc-10: an operator enters each container's passphrase at boot. Verify the
deployed generation separately; source configuration does not prove live state.
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

These are the existing **LUKS container passphrases**, not an OpenBao password
or the Linux login password. Installing OpenBao does not change them. Initial
OpenBao enrollment, repeat enrollment and password-reset limitations are
documented in [Passwords, initial enrollment and resets](openbao-local.md#passwords-initial-enrollment-and-resets).
`openbao-local rotate-unlock` does not change any LUKS passphrase. Any LUKS
credential change requires verified access/recovery and an authorized keyslot
and recovery-custody update; do not remove a working slot first.

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

Each unlock service has a 90-second execution timeout and a 120-second job
timeout, including waits for another container or backing mount. Termination
has a further 10-second bound; mapping-device waits are limited to 90 seconds.
An unanswered or hidden prompt therefore cannot indefinitely hold the splash
or login ordering. A wrong passphrase asks again, up to five attempts within
that time budget. On failure, storage-dependent services remain unavailable;
no plaintext fallback or automatic formatting is allowed. After logging in,
retry with `sudo luxnix-operator-storage start` in a private terminal. This
starts the password agent and the guarded consumers; no reboot is required.
The alternative OpenBao boot-seal prompt uses the same 90/120-second bounds.
These bounds apply to the storage unlock chain, not to unrelated boot failures. SSH is available during the
prompt: for a remote reboot, an administrator can answer it with
`sudo systemd-tty-ask-password-agent`. Already open containers are reused
without a prompt, so a rebuild or switch never asks again. This sequence has
not yet been verified by a reboot on physical hardware.

For inspection or unlock only:

```bash
sudo luxnix-operator-storage status
sudo luxnix-operator-storage open
```

### Local boot-timeout validation (2026-10-30)

The local fix bounds both container unlock and the alternative OpenBao seal
prompt. Regression coverage in `tests/test_operator_unlocked_storage.py` and
`tests/test_openbao_local.py` checks the evaluated timeouts. The existing
`operator-storage-migration` VM check now includes a separate locked-boot node:
an unanswered real LUKS prompt must time out, reach the display-manager milestone
and SSH listener, leave its guarded consumer stopped, and allow later recovery.
This checks an isolated login milestone, not the physical Predator splash.

Validation is **blocked**, not deployment-ready:

- `pytest -q tests/test_documentation_contract.py`: 26 passed.
- `nix-instantiate --parse` passed for both changed modules and the VM test.
- `python scripts/lint_structure.py`: 23 manifests passed.
- `nix eval '.#nixosConfigurations.gc-10.config.system.build.toplevel.drvPath'`
  and the evaluated storage tests fail while copying sources into the Nix store:
  `No space left on device` during rename, despite reported free disk space.
- `devenv tasks run tests:operator-storage-migration-vm` and `docs:check` cannot
  create their GC root for the same reason; the documentation test was run
  directly using the existing environment instead.
- `pytest -q tests/test_operator_storage_migration.py tests/test_documentation_contract.py --tb=short`:
  80 passed, 5 failed (atomic rename ENOSPC and rsync exit 23); it is not a passing suite.

Repair local filesystem capacity/metadata, then rerun the evaluated tests, VM
check and gc-10 build before deploying. No physical reboot validation, remote
activation, credential change or storage cleanup was performed. Without the
boot journal, this change addresses a confirmed indefinite-wait mechanism but
does not establish the cause of the reported hardware hang.

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
`luxnix-storage-provision` helper. The preview includes the selected backend,
which defaults to the host's configured unlock method:

| Backend | Prerequisites and result |
| --- | --- |
| `passphrase` | Requires the configured `passphrase` unlock policy. Creates the volume with its escrowed random passphrase; it does not require Secure Boot or enroll a TPM/OpenBao key. |
| `tpm2` | Requires Secure Boot and enrolls a TPM token. |
| `local-openbao` | Requires Secure Boot, the installed local OpenBao tools and authenticated enrollment escrow. Adds an independent OpenBao keyslot. |

An explicit `--backend` choice does not change the boot unlock policy. Both
controller and host reject passphrase provisioning under a TPM or local OpenBao
boot policy.

The passphrase and local OpenBao backends format an unpublished private
allocation with the escrowed recovery passphrase and publish only a valid
authenticated LUKS header. They create ext4 only for the authenticated new-volume
request. Existing published containers require a matching in-progress or completed
provisioning receipt; an unknown container is never adopted or reformatted by
this path. A retry resumes the same record and UUID. A partial allocation is
private staging. The local backend also writes and reads back its independent
UUID-bound OpenBao key before allocation and adds its keyslot before creating
the filesystem. The mapping stays open for subsequent pre-copy. Boot never
invokes this workflow.

### A missing container on a passphrase host

`Container missing; startup never provisions or formats storage` means the
declared container is missing at its configured path. First establish whether
this is initial provisioning or an existing volume whose backing mount or
container needs recovery. Restore that mount or container when existing data
is expected. Restarting the unlock service does not create storage.

For initial provisioning, install this revision's host helper through the normal
[existing-host deployment workflow](deployment-guide.md), and use the same
revision on the controller before applying provisioning. A switch that reports
failed storage services is not a completed deployment; repeat it successfully
after storage preparation.

For gc-02, preview the declared application volume from the controller, replacing
`<recovery-host>` with the selected independent recovery custodian:

```bash
devenv shell check-connectivity gc-02
devenv shell storage-provision provision --host gc-02 \
  --volume luxnix-app-storage --backend passphrase --recovery-host <recovery-host>
```

Review the host, machine ID, container path, existence flag and backend. Repeat
the provisioning command with `--apply` to authenticate recovery custody, create
the missing container and filesystem, and open the mapping. Inspect
`sudo luxnix-operator-storage status` on gc-02 and provision `luxnix-secrets` in
the same way if that declared volume is also missing. A successful repeat reuses
the existing escrow and matching provisioning state; do not delete records or
containers to force a fresh run.

Allocation retains the existing capacity check: each new volume reserves the
greater of its configured minimum (8 GiB by default) or twice its source-data
size plus 256 MiB, with another 256 MiB of free-space reserve. A capacity failure
requires space or layout changes; retries do not bypass it.

Once both volumes are ready, perform the existing final migration on gc-02:

```bash
sudo systemctl start luxnix-storage-cutover.service
sudo luxnix-operator-storage status
```

Cutover stops configured writers, verifies the final copy, activates the encrypted
bind mounts and restarts consumers. Source directories are retained. If migration
is already complete, `sudo luxnix-operator-storage start` uses the normal startup
path. Re-run the normal system switch and require success before considering
deployment complete.

### Provisioning from the target itself

Use `--local-target` when the controller is the target host. The selected
inventory host must exist and exactly match the local OS hostname. The preview
reports `"local_target": true` and reads the local machine ID. Target commands
then execute locally, while the recovery connection still uses SSH with strict
host-key checking. Without this option, the controller continues to use SSH for
the target; an SSH failure never selects local execution automatically.

For example, run the following as the normal administrator **on gc-02**, with
gs-02 selected as the independent recovery host:

```bash
devenv shell storage-provision provision --host gc-02 --volume luxnix-app-storage --backend passphrase --recovery-host gs-02 --local-target
```

Review the preview before adding `--apply`. Both the target and the controller
may be gc-02; the recovery host must be a different machine from both. Running
this command on gs-02 is rejected. The same local transport is available for
`storage-provision escrow` when recording an existing local volume.

Run the controller as the normal administrator so it uses that account's
existing admin vault and SSH identity. Privileged local operations still use
sudo. Immediately before applying, authenticate with `sudo -v`; if the local
sudo policy still requires a password file, supply the existing
`--sudo-password-file` option with a private file on verified encrypted or
runtime storage. A failure to obtain sudo stops the operation. The controller
does not publish recovery passphrases in command arguments or diagnostics.

Local execution uses the same installed `luxnix-storage-provision` helper as
remote execution. The earlier host-helper deployment requirement still applies.
Both recovery copies must authenticate before that helper runs; the existing
machine, container and provisioning-receipt checks remain in force. This option
does not change SSH authorization, create an admin vault, unlock an existing
container automatically, or migrate source data during a preview.

### Unlocking a newly provisioned passphrase volume after reboot

The generated recovery passphrase is also this volume's manual unlock credential.
It is independent of the Linux login password and other volumes' passphrases.
Provisioning leaves the mapping open, but a later boot needs this credential at
the systemd password prompt. Over SSH, use
`sudo systemd-tty-ask-password-agent` to answer the prompt on the target host.

The controller prints the non-secret `primary_escrow` path after provisioning.
To read that record in a private operator terminal, substitute that exact path
below. Use the same admin vault key supplied during provisioning; the example
uses its default location. Decryption validates the protected key storage and
authenticates the record. This deliberately displays the credential on the
controlling terminal, so use an unrecorded session and keep it out of chat and logs.
Enter the development environment with `devenv shell`, then run:

```bash
uv run python - /path/from/primary_escrow <<'PY'
import json
from pathlib import Path
import resource
import sys
from lx_administration.models.vault.secret import decrypt_secret

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
record = json.loads(decrypt_secret(Path(sys.argv[1]), Path.home() / ".lxv.key"))
with open("/dev/tty", "w") as terminal:
    print(f"Host: {record['host']}; volume: {record['volume']}", file=terminal)
    print(f"Container: {record['container']}; LUKS UUID: {record['luks_uuid']}", file=terminal)
    print(record["recovery_passphrase"], file=terminal)
PY
```

Confirm the displayed identity matches the intended volume before using its
passphrase. Verify this readback and independent recovery custody before rebooting.

### Escrowing existing volumes

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

Account activation follows **prepare hashes → validate enabled accounts → update
users**, before application-volume unlock. Inventory selects boot-available
hash paths under `/var/lib/luxnix-account`; storage copies existing hashes once
and preserves subsequent rotations. Local-user policy selects the file or SOPS
source; each account module owns its validator and waits for configured hash
preparation and SOPS provisioning. Admin validation is mandatory. Client
validation exists only when the client account is enabled, requires a usable
password file and has a configured path; a disabled client needs no secret or
validator. These are the one-way hashes needed by `/etc/shadow`, never plaintext
passwords, Vault keys or unlock passphrases.

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
| `migration.accountHashes` | Boot-available hash copy mapped to its source; never generates account credentials. Every activation refreshes an existing copy from its source while the source is unlocked; a locked, unsafe or retired source leaves the copy unchanged. Creating a missing copy requires a root-owned regular source with mode 0400 or 0600. |
| `volumes` | Mapping device, mount point, filesystem, optional container path, minimum size, `noexec` and backing-filesystem dependencies. |
| `bindMounts` | Logical destination to volume name and relative preserved directory. |
| `guardedServices` | Existing executable service names to required mount points; nested mounts are included. |
| `startupServices` | Guarded consumers started by the helper; timer/manual-only jobs retain their schedules. |

Before the managed-secrets client hash became 0600, it was created as 0640.
Account hashes are provisioned during activation, before the deployed
managed-secrets unit can correct that mode. A host whose switch fails with
`Boot account hash source must be a private root-owned regular file` therefore
needs one root-only copy before the first switch to the fixed revision:

```bash
sudo install -m 600 -o root -g root /etc/secrets/vault/SCRT_client_user_password_hash /var/lib/luxnix-account/client-password.hash
```

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

A failing backing disk never stops boot before networking and SSH. The module
marks every `volumes.<name>.depends` mount `nofail`, so only the unlock unit
requires it (`RequiresMountsFor`), and disables emergency mode
(`systemd.enableEmergencyMode = false`): a failed mount no longer ends in a
console `sulogin` shell. The affected volume, and the guarded services on it,
stay unavailable and fail closed; repair remotely over SSH. `depends` must not
name `/`, `/nix` or `/boot`.

## Application secrets with sops-nix

`security.sops.operatorStorageKey` replaces sync-secrets for an explicit list of
host-export application secrets. It is off by default and not enabled on any
host yet. The intended experience is one storage prompt and one normal login:

1. Local staff enter the storage passphrase for `luxnix-secrets`. This first
   unlock never depends on sops.
2. The volume opens, making the host's age key
   `/var/lib/luxnix-secrets/sops-age/keys.txt` available.
3. `sops-install-secrets.service` installs the listed secrets. It runs as a
   normal service after the unlock, never during early boot, and verifies that
   the key directory is on encrypted storage with protected swap.
4. A volume with `keyFile` (for example `luxnix-app-storage`) opens from its
   installed key, then the database and application start. These steps do not
   hold back the login screen; a failure leaves them stopped with an error
   naming the recovery command.
5. The person signs in with their own account password.

The migrated sops secrets remain protected while `luxnix-secrets` is locked:
no SSH host key or other offline-readable identity can decrypt them. This does
not protect unrelated files on an unencrypted root filesystem.

### Setup and options

Follow the production runbook
[Application secrets with sops-nix](sops-application-secrets.md); it is the only
supported setup path. The relevant options under
`security.sops.operatorStorageKey` are:

| Option | Purpose |
| --- | --- |
| `enable` | Age key on the operator volume; no SSH-key decryption; installs `luxnix-sops-storage`. |
| `secretsRepository.url`, `.rev` | Private repository pinned in inventory, fetched only when the host uses secrets. |
| `applicationSecrets.<name>` | Export names owned by sops; installed at `/etc/secrets/vault/<name>`; skipped by sync-secrets. |
| `volumeKeys.<volume>` | `"staged"` installs the key while the volume prompts; `"active"` unlocks with it. |
| `consumers` | Services that require installed secrets. |

Evaluation fails for a `keyFile` that is not a declared sops secret, a volume
key on the age key volume, `neededForUsers` secrets and account passwords.

`services.luxnix.lxAnnotateLocal.runtime.sopsMasterKey.enable` declares the
application secret `lx_annotate_master_key` at
`/run/secrets/lx_annotate_master_key` and exports that path as
`LX_ANNOTATE_MASTER_KEY_FILE`, the key lx-annotate uses for its encrypted
storage backend. It is the one application secret not installed under
`/etc/secrets/vault`: the master-key gate rejects symlinks, and sops-nix
installs its default path as a regular file.

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
