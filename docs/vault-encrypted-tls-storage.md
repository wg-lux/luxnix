# Encrypted Vault TLS storage on gs-02

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

No formatting, migration or unlock runs automatically. With the container
locked, the mount request times out after ten seconds and Vault stays down;
SSH remains available for an operator to unlock it. Never remove the storage
guard to make activation pass.

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
sudo swapoff /dev/nvme0n1p3
swapon --show=NAME,TYPE            # only RAM-only /dev/zram0 may remain
sudo stat /var/lib/luxnix-vault-pki/{ca.crt,ca.key,server.crt,server.key}
```

Stop if any existing file is missing, a symlink, or the source is already a
mountpoint. Do not start the TLS creator to fill missing files.

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

## Copy, verify, then move originals into encrypted custody

This block refuses unexpected source types, an already migrated target and a
missing mount. It compares contents without displaying private material.

```bash
sudo bash -euo pipefail <<'SH'
source=/var/lib/luxnix-vault-pki
destination=/run/luxnix-vault-tls-migration
test ! -L "$source"
! mountpoint -q "$source"
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
do not generate replacement material. After successful comparison and the
independent backup/recovery verification, move the original directory into
the encrypted volume as a retained recovery copy:

```bash
sudo mv -T /var/lib/luxnix-vault-pki /run/luxnix-vault-tls-migration/pre-migration
sudo install -d -o root -g root -m 0700 /var/lib/luxnix-vault-pki
sudo sync -f /run/luxnix-vault-tls-migration
sudo umount /run/luxnix-vault-tls-migration
```

An interrupted cross-filesystem move needs recovery from the verified copies;
do not blindly repeat it. Moving files does not erase historical plaintext
blocks, Btrfs snapshots, backups or old swap contents. Account for those copies
under the existing secret-retirement procedure; this workflow neither deletes
snapshots nor claims secure erasure.

## Activate and verify

Keep the mapping open. From the reviewed checkout **on gs-02**, persist the
configuration with native switching, not an `nh` test activation:

```bash
sudo nixos-rebuild switch --flake .#gs-02
readlink -f /run/current-system
readlink -f /nix/var/nix/profiles/system
findmnt -T /var/lib/luxnix-vault-pki -o TARGET,SOURCE,FSTYPE
swapon --show=NAME,TYPE
sudo systemctl start vault.service nginx.service
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

Retry `managed-secrets-setup.service` only after Vault is unsealed and its own
credential/storage prerequisites pass. This TLS migration does not encrypt
unrelated managed-secret destinations. A remaining failure there must be
reported separately; it is not grounds to bypass its guard.

## After each reboot

From an authenticated SSH session on gs-02:

```bash
sudo cryptsetup open --type luks /var/lib/luxnix-vault-tls.luks luxnix-vault-pki
sudo systemctl start vault.service nginx.service
```

Then use the CA-verified status and hidden unseal sequence above. If the mapping
is already open, verify its backing file and mount instead of reopening it.
Do not roll back to a generation that re-enables plaintext disk swap. Recovery
uses the verified encrypted container/archive and the existing CA and unseal
shares, never fresh initialization.
