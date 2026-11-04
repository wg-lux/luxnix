# Unmigrated hosts: legacy storage until boot-LUKS

The fleet target is [boot LUKS](boot-storage-migration.md), installed with the
[operator checklist](boot-storage-operator.md). gc-10 explicitly retains its
existing containers at the owner's request. This page is
only for hosts that still run the older layout. It covers operating and
recovering them until they are reinstalled, then it stops applying. It is not
an installation, enrollment or provisioning path.

| Host | Repository configuration | Old live storage to preserve |
| --- | --- | --- |
| gc-09 | `boot-luks` since 2026-11-03; the installed generation still runs containers | `luxnix-secrets` and `luxnix-app-storage` containers |
| gc-10 | `legacy-containers`: preserve existing partitions and unlock through Plymouth | Containers listed in [gc-10](#gc-10) |
| gs-02 | `boot-luks`; the Vault TLS container option evaluates off | `/var/lib/luxnix-vault-tls.luks` holding Vault PKI and managed secrets |

gc-09 cannot be rebuilt in place with its plaintext root under the boot-LUKS
policy. gc-10 explicitly retains its existing container layout; migration is
disabled and rebuilding does not repartition or move application data.

The repository describes intent, not live state. Inspect the host before
acting. Do not activate the boot-LUKS configuration on an old disk layout: it
does not convert storage (see [temporary compatibility](boot-storage-migration.md#temporary-compatibility-and-removal)).

## Rules until migration is accepted

- Keep every existing container, LUKS keyslot, recovery record, OpenBao seal
  record and Raft state. Never delete or reformat one to resolve an unlock error.
- Do not start new TPM, OpenBao, network-release or login-unlock enrollment.
  These paths are frozen; their apply commands are rejected.
- No plaintext fallback: a missing or locked volume keeps its services stopped.
- Keep disk swap disabled; only RAM-only zram may remain. Do not roll back to a
  generation that re-enables disk swap.
- A NixOS generation rollback does not undo keyslot changes, formatting or
  database migrations.
- Never put a passphrase in chat, command arguments, inventory or logs.

## Unlocking gc-09 and gc-10 at boot

Unlock policy is shared across hosts, without a hostname allowlist. Selecting
`legacy-containers` with passphrase-protected volumes enables Plymouth and
orders their unlock before the display manager and password-agent shutdown.
Inventory supplies the installed layout, container paths, UUIDs and mounts;
passwords remain private operator credentials. This configuration never converts
an existing plaintext partition into LUKS or provisions a new container at boot.

The configured method is `unlockMethod = "passphrase"`. The boot splash, or the
console, asks `Unlock luxnix-app-storage:` and then `Unlock luxnix-secrets:`.
These are the LUKS container passphrases, not the login password and not an
OpenBao password. When both containers share a passphrase, the second prompt is
skipped. The volumes then open and PostgreSQL and LX-Annotate start. The account
password only logs the user in.

Container unlocks finish before `systemd-ask-password-wall.service` starts:
its startup stops the Plymouth agent. Starting it earlier hides pending splash
prompts and leaves the unlock services waiting until their timeout.

Each unlock service is bounded: 90 seconds execution, 120 seconds job timeout,
up to five attempts. On failure the storage-dependent services stay stopped and
login still appears. To recover without rebooting, run this in a private terminal:

```bash
sudo luxnix-operator-storage status
sudo luxnix-operator-storage start     # one password agent, then guarded services
sudo luxnix-operator-storage open      # unlock only
```

During a remote reboot, answer the prompt over SSH with
`sudo systemd-tty-ask-password-agent`. Open containers are reused, so a rebuild
or switch does not ask again.

When startup fails, inspect `luxnix-storage-unlock-*.service`,
`luxnix-storage-migrate.service` and `luxnix-storage-check-*.service`, then
`findmnt` sources, Vault enrollment, PostgreSQL and HTTPS. Old interim units
under `/etc/systemd/system.control` take precedence over generated units. Retire
only the overrides that the reviewed configuration replaces, while writers are
stopped.

On gc-10, the 2026-11-04 boot ran the newly staged generation but still loaded
old native `.mount` files from `/etc/systemd/system.control`. Those files omitted
the generated unlock dependencies and `nofail`, making `local-fs.target` wait for
a locked device while the unlock waited for `local-fs.target`. The 90-second
device timeout left only 30 seconds of the queued unlock job before Plymouth
stopped. This is stale host-local configuration, not evidence of a bad password
or of the new generation failing to boot. Check the active definition with:

```bash
systemctl show 'var-lib-luxnix\x2dapp\x2dstorage.mount' -p FragmentPath
systemctl cat 'var-lib-luxnix\x2dapp\x2dstorage.mount'
```

The reviewed fstab-backed replacement should load from `/run/systemd/generator/`.
Preserve a backup and retire only matching interim overrides, including nested
binds, during a stopped-writer maintenance window; do not delete the whole
`system.control` directory. A theme change or longer password timeout cannot
repair a mount definition that still shadows the declared configuration.

### Hidden nested secret mounts

A live switch can add a parent bind, such as `/etc/secrets`, while a child bind
such as `/etc/secrets/vault` is already mounted. systemd then mounts the parent
over the child: `etc-secrets-vault.mount` still reports `active` and
`findmnt /etc/secrets/vault` still lists the stale entry, but the path is no
longer a mount point. The journal shows `Directory /etc/secrets to mount over is
not empty`, and `luxnix-storage-check-vault-auth-setup.service` fails with
`Assertion failed`. That assertion is correct. Do not remove it. Trust
`mountpoint /etc/secrets/vault` over `findmnt` here.

Each storage check pulls in `luxnix-storage-restack.service`, which repairs
exactly this state. It identifies mounts by kernel mount ID. It bind-mounts only
the configured encrypted source on top of a verified encrypted parent, and
creates only the missing final directory. It refuses to act while a writer
guarding that path is running, and it never creates a bind source. On a cold
boot it does nothing. To repair manually after stopping affected writers:

```bash
sudo systemctl start luxnix-storage-restack.service
sudo luxnix-operator-storage start
```

The hidden stale entry remains below the parent until the next reboot. Reboot
before locking or closing the containers.

### Local OpenBao on these hosts

`openbao.local.enable` installs the retained OpenBao recovery tooling. It does
not change the container unlock method. Check what is actually enrolled before
choosing any operation:

```bash
devenv shell openbao-local status --limit <host> [--sudo-password-file <private-file>]
```

An inactive service does not prove that no enrollment or Raft data exists.
If a host was enrolled with the passphrase seal, the boot prompt for it has the
same 90/120-second bounds; after exhausted attempts restart
`openbao-local-seal-key.service`, then start the storage unlock units.

- **Lost OpenBao boot passphrase:** there is no reset command. Preserve the
  wrapped record in `/var/lib/openbao-bootstrap/`, the Raft state and the
  containers. The retained LUKS recovery passphrases below are the independent
  route to the data. Do not reinitialize OpenBao.
- **`interrupted-initialization`:** the store holds no data and its recovery
  key was never escrowed. Stop `openbao-local.service`, move
  `/var/lib/openbao-local` aside for inspection, then contact the storage owner.
  New enrollment is retired, so do not rerun it to repair this.
- `openbao-local rotate-unlock` replaces an AppRole SecretID only. It never
  changes the boot passphrase, the seal key or any LUKS passphrase.

## Recovery credentials

Each container has a random recovery passphrase, which is also its manual
unlock credential. It is stored as an authenticated Ansible Vault record under
`~/.lxv/storage-recovery/<machine-id>/<volume>.vault` on the controller. An
encrypted copy is on the recovery host under
`~/.luxnix-recovery/<machine-id>/<luks-uuid>.vault`. Both use the same admin
vault key, so an independent age copy is needed as well.

Read a record in an unrecorded private terminal inside `devenv shell`. Confirm
the displayed host, volume and LUKS UUID before using the passphrase:

```bash
uv run python - /path/to/<volume>.vault <<'PY'
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

Escrow an existing container that has no record yet. The existing credential is
tested; keyslots and data are not changed. Omit `--apply` to inspect:

```bash
devenv shell storage-provision escrow --host <host> --volume <volume> \
  --recovery-host <host> --existing-key-file <private-file> [--apply]
```

Prepare and verify independent custody. It is needed for the
[restore step](boot-storage-migration.md#reprovision-and-restore-explicit-destructive-operator-action):

```bash
devenv shell storage-recovery-custody prepare \
  --identity <controller-age-identity> \
  --custodian-identity <independent-age-identity> \
  --vault-dir <existing-admin-vault> \
  --export-directory <independent-encrypted-directory>
devenv shell storage-recovery-custody verify \
  --identity <controller-age-identity> --custodian-identity <independent-age-identity>
devenv shell storage-recovery-custody export-vault-record \
  --source <existing-volume.vault> --vault-key <existing-admin-vault-key> \
  --custodian-identity <independent-age-identity> \
  --destination <independent-encrypted-directory/volume.age>
```

`export-vault-record` publishes only age ciphertext, checks readback and refuses
to replace a different existing envelope. Do not delete old keys or records to
force a retry.

`sudo luxnix-operator-storage header-backup <mapping> <destination-file>` writes
a LUKS header backup to a new file. Keep it on independent encrypted recovery
storage. A header backup retains every keyslot present when it was created, so
replace it after keyslot changes.

## gc-10

The operator retained this layout on 2026-11-04. `/data/raid01` remains its
existing Btrfs filesystem; Plymouth unlocks the container file inside it.
The password supplied privately for this host was added to both containers,
with the original recovery keyslots retained. Enter that password at the splash;
the shared in-memory password cache lets the second container reuse it.
No passphrase belongs in inventory, the Nix store, or an installed key file.

| Volume | Existing container | Required LUKS UUID |
| --- | --- | --- |
| luxnix-app-storage | `/data/raid01/luxnix-app-storage.luks` | `f5869d54-4ea5-407c-a690-7238fe79cd6b` |
| luxnix-secrets | `/var/lib/luxnix-secrets.luks` | `dc53d362-e6e2-43ee-9cbf-4726d55c3055` |

Keep application master keys, salts and the database together: a successful
unlock does not prove application decryption. Recovery custody is the
encrypted admin vault on gc-02 (`~/.lxv`) and an export on gs-02
(`~/.luxnix-recovery`). A copy outside both gs-02 and gc-10 is still required
before reprovisioning. Private controller inputs are `/home/admin/pwd_gc-10.txt`
(sudo), `/home/admin/Desktop/token-gc-10-enc.txt` (application container) and
`/home/admin/Desktop/token-gc-10.txt` (secrets container). They are never boot
or repository inputs. gc-10 has no recovery console. Use
`ansible/playbooks/storage-legacy-recovery.yml` as described in
[temporary compatibility](boot-storage-migration.md#temporary-compatibility-and-removal).

### Local Backup export mount

The operator authorized plaintext annotation export copies on gc-10's existing
Backup disk. Only
`/var/lib/lx-annotate/data/storage/frame_annotation_exports` is affected, bound
from `/run/media/admin/Backup-24-11/lx-annotate-exports` by the host's
`backup-exports.nix`. Evidence is in
`feature-tracking/lx_annotate_environment_lifecycle_audit.yaml`
(`gc10_local_backup_exports`). The external copies must stay under the
operator's physical control.

The mount activates on access and fails without writing to the application disk
when the disk is missing. If a temporary bind blocks the automount, confirm no
export is running, then:

```sh
sudo systemctl stop 'var-lib-lx\x2dannotate-data-storage-frame_annotation_exports.mount'
sudo systemctl start 'var-lib-lx\x2dannotate-data-storage-frame_annotation_exports.automount'
sudo systemctl start --no-block lx-annotate.service lx-annotate-celery-ffmpeg-worker.service
```

`--no-block` only schedules startup, so check both services afterwards. Stop
export activity before removing the disk. After reconnecting, run
`systemctl reset-failed` for `gc10-backup-exports-prepare.service` and the
export mount. Never force an unmount or move export files.

## gs-02 Vault container

Until gs-02 is reinstalled, its live Vault CA, server leaf, managed secrets,
enrollment bundles, site lifecycle state and identity-salt recovery copies are
in the manually unlocked container `/var/lib/luxnix-vault-tls.luks`. Vault's
Raft data stays in `/var/lib/vault`, protected by the Vault barrier. The
container passphrase and Vault unseal shares are separate credentials.

After each reboot, from an authenticated SSH session on gs-02:

```bash
sudo cryptsetup open --type luks /var/lib/luxnix-vault-tls.luks luxnix-vault-pki
sudo systemctl start etc-secrets-vault.mount vault.service
for path in /var/lib/luxnix-vault-site-lifecycle /root/vault-enrollment; do
  sudo systemctl start "$(systemd-escape --path --suffix=mount "$path")" || break
done
```

If the mapping is already open, verify its backing file and mount instead.
Then [check and unseal Vault](vault-hub-machine-enrollment.md#check-and-unseal-vault).
After that, restart managed-secret setup, then restore CA publication and the
applications in that order. Starting `lx-annotate-identity-salts.service` pulls
in both salt recovery mounts. Verify encrypted placement with:

```bash
sudo python3 lx_administration/secret_storage.py --allow-runtime \
  /run /var/lib/luxnix-vault-site-lifecycle /root/vault-enrollment \
  /etc/secrets/vault/hub-pki
```

Recovery always uses the existing container, CA and unseal shares. Never
initialize Vault or create a new CA to make a service start. If two CAs are
found, preserve both sets in separate root-only directories on the encrypted
volume. Identify the original from trusted deployment evidence by SHA-256
fingerprint and key match, not by subject. The 2026-10-23 migration restored
the original August CA after TLS maintenance had created a different one.

## Back to normal

1. Take snapshots and verified, restorable backups:
   [snapshot backups](boot-storage-migration.md#snapshot-backups-from-the-existing-gc-09-and-gc-10-installations)
   and, on gs-02, [coordinated hub snapshots](boot-storage-migration.md#coordinated-hub-snapshots).
2. Reinstall with the [operator checklist](boot-storage-operator.md) and restore
   data and keys into the boot-LUKS layout.
3. Pass cold-boot and [acceptance checks](boot-storage-migration.md#acceptance-recovery-and-rollback-limits).
4. Remove the host's `legacy-containers` exception through Autoconf, keeping
   old disks until retention removal is approved separately.

When no host needs this page any more, delete it together with the
legacy-only metadata and tests.
