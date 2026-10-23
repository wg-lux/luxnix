# Encrypted Vault TLS and managed-secret storage on gs-02

This migrates the **existing** server CA and leaf into a manually unlocked
LUKS2 container. It does not initialize Vault, replace its CA, rotate identity
salts, repartition a disk, or move the barrier-encrypted Raft data in
`/var/lib/vault`. The container passphrase and Vault unseal shares are separate
credentials, held in independent approved recovery custody.

The canonical gs-02 inventory enables
`luxnix.vault.server.managedTls.encryptedStorage`, disables disk swap and
hibernation, and retains RAM-only zram. The module mounts the opened
`/dev/mapper/luxnix-vault-pki` device at `/var/lib/luxnix-vault-pki`.
Vault and TLS maintenance require that mount and stop when it is removed.
The existing storage verifier still checks encrypted ancestry and swap.
Other hosts retain their existing storage configuration.

gs-02 also masks `systemd-gpt-auto-generator`: an empty `swapDevices` list
alone does not prevent systemd from rediscovering the existing GPT swap
partition. After applying the configuration, verify `swapon --show=NAME,TYPE`
and stop any remaining disk swap with `sudo swapoff /dev/nvme0n1p3` after
checking available memory. Only RAM-only zram may remain.

No formatting, migration or unlock runs automatically. With the container
locked, the mount request times out after ten seconds and Vault stays down;
SSH remains available for an operator to unlock it. Never remove the storage
guard to make activation pass.

The operator confirmed successful activation after applying the managed-secret
bind-mount patch on 2026-10-23. This records the gs-02 migration outcome; it
does not establish fleet enrollment, reboot recovery or retirement of historical
plaintext copies. For this migrated host, use the reboot/recovery sections
instead of repeating container creation or copying.

## Prepare the reviewed generation

From the durable LuxNix checkout on the controller:

```bash
nix eval '.#nixosConfigurations.gs-02.config.system.build.toplevel.drvPath'
nix build '.#nixosConfigurations.gs-02.config.system.build.toplevel' --no-link
devenv shell check-connectivity gs-02
```

Record the checkout commit, local changes and `flake.lock` hash. Use that same
reviewed source for the final switch. The following commands run **on gs-02**,
as an authorized administrator with sudo and recovery access. They need
`cryptsetup`, `mkfs.ext4`, `chattr`, `fallocate`, `openssl` and `age`.
Check their availability before the outage. The new configuration includes
`cryptsetup`; do not activate it merely to obtain migration tools.
Changes made on the controller are not automatically present in the target
checkout. Transfer the reviewed commit or patch, including the generated host
file, to `~/dev/luxnix` on gs-02 **before** switching. For a supplied patch:

```bash
cd ~/dev/luxnix
git apply --check gs-02-encrypted-managed-secrets.patch
git apply gs-02-encrypted-managed-secrets.patch
```

Stop if the check fails; do not force it or overwrite unrelated changes. If
applying the canonical YAML manually, regenerate using the documented
Autoconf workflow. Confirm the target checkout evaluates the intended bind source:

```bash
nix eval --raw '.#nixosConfigurations.gs-02.config.fileSystems."/etc/secrets/vault".device'
```

Expected: `/var/lib/luxnix-vault-pki/managed-secrets`. A missing option means
this checkout does not contain the required configuration. Rebuilding the old
checkout cannot fix the missing mount.

Stop immediately on a failed command or verification, except the documented
sealed-Vault status exit below. Do not paste subsequent stages after a failure.

## Quiesce and preserve

Check available memory before disabling disk swap; do not force the operation
if swapoff fails. Stop TLS writers and certificate consumers for the migration:

```bash
hostname                         # must be gs-02
free -h
swapon --show=NAME,TYPE,SIZE
sudo systemctl stop luxnix-vault-managed-server-tls.timer
sudo systemctl stop vault.service nginx.service luxnix-vault-managed-server-tls.service
# Only if /dev/nvme0n1p3 is listed as active swap and memory is sufficient:
sudo swapoff /dev/nvme0n1p3
swapon --show=NAME,TYPE            # only RAM-only /dev/zram0 may remain
sudo stat /var/lib/luxnix-vault-pki/{ca.crt,ca.key,server.crt,server.key}
```

If only zram is listed, skip `swapoff`; `Invalid argument` for an inactive
partition is not a migration failure.

Before opening a new container, prevent automatic mounting at the original
TLS path. Otherwise TLS maintenance can create a different CA on the empty
volume and hide the original files:

```bash
unit=$(systemd-escape --path --suffix=mount /var/lib/luxnix-vault-pki)
sudo systemctl mask --runtime --now "$unit"
systemctl show "$unit" -p LoadState
findmnt -T /var/lib/luxnix-vault-pki -o TARGET,SOURCE,FSTYPE
```

Require `LoadState=masked` and the original Btrfs filesystem at the TLS path.
Keep the mask until the copy is verified. Stop if any original file is missing
or a symlink. Do not start the TLS creator to fill missing files. Do not reboot
during migration: a runtime mask does not survive reboot.

Create an encrypted preservation archive with the existing
`luxnix-vault-prepare-server-rebuild` command, using an independently held
offline age recipient and a protected output directory. This command only
archives; its name does not authorize a Vault reset. Follow
[the encrypted archive procedure](vault-server-rebuild.md#2-create-an-encrypted-preservation-archive).
Require independent decryption/listing verification before moving originals.
Keep the passphrase and recovery material out of shell arguments, environment
files, the repository and the Nix store.

## Create the new container once

Use `/var/lib/luxnix-vault-tls.luks` for this installation. Refuse an existing
file or mapper: after an interruption, inspect and recover the existing
container instead of repeating formatting.
Run the complete `sudo bash` block below: `set` is a shell builtin, and file
redirection must run inside the root shell. `sudo set` cannot elevate it.

```bash
sudo test ! -e /dev/mapper/luxnix-vault-pki
sudo bash -euo pipefail <<'SH'
test ! -e /var/lib/luxnix-vault-tls.luks
test ! -L /var/lib/luxnix-vault-tls.luks
umask 077
set -o noclobber
: > /var/lib/luxnix-vault-tls.luks
# gs-02 uses Btrfs: set NOCOW before allocating the new, empty file.
chattr +C /var/lib/luxnix-vault-tls.luks
fallocate -l 256M /var/lib/luxnix-vault-tls.luks
SH
sudo cryptsetup luksFormat --type luks2 /var/lib/luxnix-vault-tls.luks
sudo cryptsetup open --type luks /var/lib/luxnix-vault-tls.luks luxnix-vault-pki
sudo cryptsetup status luxnix-vault-pki
```

Verify that the mapping's backing file is the newly created container before
the next command. Enter its passphrase only through cryptsetup's hidden prompt.
Formatting below applies **only to this new mapping**:

```bash
sudo mkfs.ext4 /dev/mapper/luxnix-vault-pki
sudo install -d -m 0700 /run/luxnix-vault-tls-migration
sudo mount -o nodev,nosuid,noexec /dev/mapper/luxnix-vault-pki /run/luxnix-vault-tls-migration
```

Back up the LUKS header and verify passphrase recovery in approved custody
before retiring any original. Do not use a key file on gs-02's unencrypted root.

## Copy and verify without moving the originals

This block refuses unexpected source types, an already migrated target and a
missing mount. It compares contents without displaying private material.

```bash
sudo bash -euo pipefail <<'SH'
source=/var/lib/luxnix-vault-pki
destination=/run/luxnix-vault-tls-migration
test ! -L "$source"
if mountpoint -q "$source"; then
  echo "STOP: original directory is hidden by a mount."
  exit 1
fi
mountpoint -q "$destination"
test "$(findmnt -nr -o SOURCE --target "$destination")" = /dev/mapper/luxnix-vault-pki
test -z "$(find "$source" ! -type f ! -type d -print -quit)"
test ! -e "$destination/ca.key"
test ! -e "$destination/pre-migration"
for name in ca.crt ca.key server.crt server.key; do
  test -s "$source/$name"
done
cp -a "$source/." "$destination/"
diff -qr --no-dereference --exclude=lost+found "$source" "$destination"
for name in ca.crt ca.key server.crt server.key; do
  test "$(stat -c '%u:%g:%a' "$source/$name")" = "$(stat -c '%u:%g:%a' "$destination/$name")"
done
openssl verify -CAfile "$destination/ca.crt" -purpose sslserver "$destination/server.crt"
sync -f "$destination"
SH
```

If verification fails, leave both copies intact and Vault stopped. Investigate;
do not generate replacement material. A successful block prints the OpenSSL
`server.crt: OK` result and exits zero. Do not infer success from an empty prompt.

Keep the original directory in place for recovery; **do not use `mv -T`**.
The final mount will hide it. After verification:

```bash
sudo sync -f /run/luxnix-vault-tls-migration
sudo umount /run/luxnix-vault-tls-migration
unit=$(systemd-escape --path --suffix=mount /var/lib/luxnix-vault-pki)
sudo systemctl unmask --runtime "$unit"
sudo systemctl daemon-reload
sudo systemctl start "$unit"
findmnt -T /var/lib/luxnix-vault-pki -o TARGET,SOURCE,FSTYPE
```

If the mount unit is not installed yet, mount the verified mapper at the final
path manually before the first activation. Require ext4 on the intended mapper.
Complete the managed-secret preparation below before switching the generation.
Historical plaintext files, Btrfs snapshots, backups and old swap contents
remain subject to the existing secret-retirement procedure. Mounting encrypted
copies does not erase those originals.

### Recover from an interrupted or automatically remounted migration

If both TLS paths resolve to the same mapper, a successful comparison only
compares the volume with itself. Stop services, mask the final mount as above,
and confirm the original path resolves to Btrfs before comparing again.
`into itself` or `Directory not empty` from `mv` is a reason to stop, not to
remove a recovery directory or repeat the move.

If the CAs differ, compare public certificate fingerprints and dates with
`openssl x509 -noout -dates -fingerprint -sha256`. Preserve each set in its own
uniquely named, root-only recovery directory on the encrypted volume. Identify
the original CA from trusted deployment evidence; a matching subject is not
proof of identity. Verify certificate/private-key public-key matches and the
leaf chain before restoring the original four files. Never print private keys.
The observed migration required restoring the original August CA after TLS
maintenance created a different CA in October. Neither Vault initialization nor
fleet CA replacement was needed.

## Bind the existing managed secrets into encrypted storage

gs-02 now declares `/etc/secrets/vault` as a bind mount of
`/var/lib/luxnix-vault-pki/managed-secrets`. It requires the LUKS filesystem
first. Managed-secret generation requires the bind mount and stops if it
disappears; application services retain their existing managed-secret dependencies.
This configuration does not migrate or generate the source directory.

Stop triggers before services; stopping a service alone does not stop its
socket, path or timer from starting it again:

```bash
sudo systemctl stop 'lx-annotate*.timer' lx-annotate-request-throttle.socket lx-annotate-filewatcher.path
sudo systemctl stop 'lx-annotate*.service' nginx.service managed-secrets-setup.service
```

Also stop enrollment/synchronization jobs and preserve a verified encrypted backup. With
the LUKS filesystem mounted and `/etc/secrets/vault` still on its original
filesystem, copy that directory using `cp -a` into the previously nonexistent
`managed-secrets` destination. Refuse unexpected symlinks or nested mounts.
Compare contents with `diff -qr --no-dereference` and compare relative paths,
types, modes, numeric owners and groups. Stop on any mismatch; do not overwrite
an existing destination or move the originals. Keep all writers stopped until
activation. The original directory remains hidden beneath the bind mount for
recovery; this does not erase its historical plaintext contents.

## Activate and verify

Keep the mapping open. From the reviewed checkout **on gs-02**, persist the
configuration with native switching, not an `nh` test activation:

```bash
sudo nixos-rebuild switch --flake .#gs-02
readlink -f /run/current-system
readlink -f /nix/var/nix/profiles/system
findmnt -T /var/lib/luxnix-vault-pki -o TARGET,SOURCE,FSTYPE
swapon --show=NAME,TYPE
sudo systemctl start etc-secrets-vault.mount
findmnt -T /etc/secrets/vault -o TARGET,SOURCE,FSTYPE
sudo systemctl restart managed-secrets-setup.service
sudo systemctl start vault.service
sudo systemctl start luxnix-vault-managed-server-tls.timer
systemctl is-active vault.service
export VAULT_ADDR=https://172.16.255.22:8200
export VAULT_CACERT=/var/lib/luxnix-vault-pki/ca.crt
export VAULT_TLS_SERVER_NAME=vault.endo-reg.net
vault status
```

The active and persistent generation paths must match. The TLS directory must
be an ext4 mount on the LUKS mapper; no disk swap may remain. A reachable,
initialized but sealed Vault is expected after restart (`vault status` exits 2
when sealed). Unseal through the existing hidden `vault operator unseal`
prompt, then verify `vault status` succeeds with `Sealed: false`.
Never run `vault operator init` for this migration.

The managed-secret source must be
`/dev/mapper/luxnix-vault-pki[/managed-secrets]`, not the root Btrfs filesystem.
If another secret destination or credential fails verification, resolve that
specific error without weakening the guard. A failed activation can still
change mounts and restart triggers; inspect current state before any retry.
Do not copy secrets again over an active bind mount.

Once Vault is unsealed and managed-secret setup succeeds:

```bash
sudo systemctl restart luxnix-vault-publish-hub-client-ca.service
sudo systemctl start nginx.service lx-annotate.service
sudo systemctl start lx-annotate-request-throttle.socket lx-annotate-filewatcher.path
```

Restore the previously active application timers/workers through the normal
application startup workflow. Confirm application health before fleet enrollment.
TLS maintenance is a oneshot: `inactive` with `Result=success` and exit status 0
is normal. Vault health/publication failures while sealed require unsealing,
not replacement TLS material. Inspect failures with:

```bash
sudo journalctl -u managed-secrets-setup.service -u luxnix-vault-managed-server-tls.service -n 60 --no-pager
systemctl show managed-secrets-setup.service -p RequiresMountsFor -p BindsTo
systemctl show etc-secrets-vault.mount -p LoadState
```

If the bind mount is `not-found` and those dependencies are empty, first verify
the target checkout includes the reviewed patch. Native switching requires
`sudo`; an unprivileged profile symlink error occurs before activation. The
observed failing `nh` test activations left the persistent profile unchanged.
Always compare the active and persistent generation links after switching.

## Bind the existing managed secrets into encrypted storage

gs-02 now declares `/etc/secrets/vault` as a bind mount of
`/var/lib/luxnix-vault-pki/managed-secrets`. It requires the LUKS filesystem
first. Managed-secret generation requires the bind mount and stops if it
disappears; application services retain their existing managed-secret dependencies.
This configuration does not migrate or generate the source directory.

Before activating this configuration, stop enrollment/synchronization jobs,
the lx-annotate timers, `lx-annotate-request-throttle.socket` and
`lx-annotate-filewatcher.path`, then lx-annotate services, nginx and
`managed-secrets-setup.service`. Preserve a verified encrypted backup. With
the LUKS filesystem mounted and `/etc/secrets/vault` still on its original
filesystem, copy that directory using `cp -a` into the previously nonexistent
`managed-secrets` destination. Refuse unexpected symlinks or nested mounts.
Compare contents with `diff -qr --no-dereference` and compare relative paths,
types, modes, numeric owners and groups. Stop on any mismatch; do not overwrite
an existing destination or move the originals. Keep all writers stopped until
activation. The original directory remains hidden beneath the bind mount for
recovery; this does not erase its historical plaintext contents.

After the copy and metadata comparison pass, use the reviewed checkout on gs-02:

```bash
sudo nixos-rebuild switch --flake .#gs-02
sudo systemctl start etc-secrets-vault.mount
findmnt -T /etc/secrets/vault -o TARGET,SOURCE,FSTYPE
sudo systemctl restart managed-secrets-setup.service
```

The source must be the LUKS mapper's `managed-secrets` subdirectory, not the
root Btrfs filesystem. A failed activation does not mean nothing changed:
inspect the mount and failed-unit journal before retrying. If managed-secret
generation fails for another destination or credential, stop and resolve that
specific failure without weakening its guard. Once it succeeds, start
`lx-annotate.service`, nginx and the previously stopped application triggers
through the normal application startup workflow. Verify Vault is unsealed,
the application is healthy, and active/persistent generations match before
fleet enrollment. Do not run another secret copy over the mounted destination.

## Protect saved enrollment bundles and lifecycle state

Fleet enrollment also requires encrypted storage for
`/var/lib/luxnix-vault-site-lifecycle` and `/root/vault-enrollment`. The gs-02
inventory binds these to `site-lifecycle` and `site-enrollment` under the
existing LUKS filesystem. The mounts are `noauto`: start them explicitly after
manual unlock and before any enrollment/lifecycle operation. This does not
move `/var/lib/vault` or change any saved identity.

Stop all enrollment, rotation, containment and reconciliation commands before
copying, and keep them stopped until verification and mounting finish. Preserve
a verified encrypted backup. Run this once on gs-02; it refuses existing
destinations, symlinks, special files and mounted sources. Never interpret a
zero `du` allocation as proof that a lifecycle directory is empty.

```bash
sudo bash -euo pipefail <<'SH'
base=/var/lib/luxnix-vault-pki
mountpoint -q "$base"
test "$(findmnt -nr -o SOURCE --target "$base")" = /dev/mapper/luxnix-vault-pki
sources=(/var/lib/luxnix-vault-site-lifecycle /root/vault-enrollment)
destinations=("$base/site-lifecycle" "$base/site-enrollment")
for i in 0 1; do
  source=${sources[$i]}
  destination=${destinations[$i]}
  test -d "$source"
  test ! -L "$source"
  if mountpoint -q "$source"; then
    echo "STOP: source is already mounted: $source"
    exit 1
  fi
  test -z "$(findmnt -rn -o TARGET | awk -v p="$source/" 'index($0,p)==1')"
  test -z "$(find "$source" ! -type f ! -type d -print -quit)"
  test ! -e "$destination"
  test ! -L "$destination"
done
for i in 0 1; do
  source=${sources[$i]}
  destination=${destinations[$i]}
  cp -a "$source" "$destination"
  diff -qr --no-dereference "$source" "$destination"
  diff -q \
    <(cd "$source"; find . -printf '%P %y %m %U %G\n' | LC_ALL=C sort) \
    <(cd "$destination"; find . -printf '%P %y %m %U %G\n' | LC_ALL=C sort)
done
sync -f "$base"
echo "Both encrypted copies verified; originals unchanged."
SH
```

If interrupted, preserve all copies and compare before resuming; do not delete
or overwrite an existing destination. Transfer the reviewed configuration patch
to the durable gs-02 checkout, check/apply it, and persist the generation with
`sudo nixos-rebuild switch --flake .#gs-02`. Then start and inspect the mounts:

```bash
for path in /var/lib/luxnix-vault-site-lifecycle /root/vault-enrollment; do
  sudo systemctl start "$(systemd-escape --path --suffix=mount "$path")" || break
  sudo findmnt -T "$path" -o TARGET,SOURCE,FSTYPE
done
sudo python3 lx_administration/secret_storage.py --allow-runtime \
  /run /var/lib/luxnix-vault-site-lifecycle /root/vault-enrollment \
  /etc/secrets/vault/hub-pki
```

Run the verifier from the gs-02 checkout; success is silent with exit status 0.
Both persistent mounts must show the LUKS mapper and their respective
subdirectories. Keep originals underneath for recovery and separately retire
historical plaintext copies. Review and commit the configuration changes, keep
any downloaded patch outside the checkout, and require a clean worktree before
rerunning the scoped enrollment command. The corrected preflight must check
`/var/lib/luxnix-vault-site-lifecycle`, not `/var/lib/vault/site-lifecycle`.

## After each reboot

From an authenticated SSH session on gs-02:

```bash
sudo cryptsetup open --type luks /var/lib/luxnix-vault-tls.luks luxnix-vault-pki
sudo systemctl start etc-secrets-vault.mount vault.service
for path in /var/lib/luxnix-vault-site-lifecycle /root/vault-enrollment; do
  sudo systemctl start "$(systemd-escape --path --suffix=mount "$path")" || break
done
```

Then use the CA-verified status and hidden unseal sequence above, restart
managed-secret setup, and restore CA publication and applications in that order.
If the mapping is already open, verify its backing file and mount instead of reopening it.
Do not roll back to a generation that re-enables plaintext disk swap. Recovery
uses the verified encrypted container/archive and the existing CA and unseal
shares, never fresh initialization.
