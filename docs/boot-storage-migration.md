# Boot LUKS storage: migration and recovery

## Architecture and scope

The final fleet layout is `luxnix.storage.operatorUnlocked.layout = "boot-luks"`
(the default). EFI remains unencrypted. One LUKS2 root mapping opens in the
systemd initrd with the operator credential. Root contains `/nix`, homes,
persistent logs, temporary files, service secrets and secondary disk keyfiles.
The stage-2 crypttab generator opens independent data mappings with those
keyfiles. No secondary key is embedded in the initrd, EFI or Nix store. Normal
boot requires neither Git nor a network key service. Authentication to the
normal user account follows storage unlock; these credentials are independent.
Secure Boot signing remains a separate boot policy. Encryption does not provide
integrity protection for arbitrary root filesystem contents.

Host disk definitions own device identifiers and subvolumes. The shared
`systems/x86_64-linux/encrypted-layout.nix` applies the same LUKS2 policy to all
15 operator-storage hosts, including every member of multi-device Btrfs arrays.
The shared storage module creates crypttab and guarded service dependencies.
gc-10 keeps application, PostgreSQL and database-backup state on its second disk
as directly mounted Btrfs subvolumes. Other host layouts retain their declared
data filesystems. Application paths stay unchanged, but become ordinary directories instead of
inner container mounts. PostgreSQL data/WAL/backups, LX-Annotate media, frames,
processing state, keys, retained salts, caches and local logs belong on this
protected storage. Alternate paths must be included in guardedServices and
must resolve to encrypted storage; do not add plaintext independent disks.
Memory temporary storage is acceptable only with encrypted or disabled disk
swap. gc-10's declared swap partition is **not active**: its explicit empty
swapDevices policy remains. Existing encrypted-root swapfiles remain encrypted.

The verifier checks mounted device identity, encryption ancestry, Btrfs members,
active swap and existing secondary key permissions. Missing storage stops service
startup; dependencies also stop consumers before unmount. Secondary unlocks are
headless and device waits bounded. Use the local console and `journalctl -b`
for storage/recovery errors. No boot unit formats, migrates or generates keys.
The pre-switch check rejects an unencrypted or incompletely mounted installation
before the normal NixOS switch/boot operation. A build, password prompt or warm
activation does not prove physical encryption. Do not bypass pre-switch checks
or install a bootloader manually on an unmigrated host.

Exports and remote backups are independent protection boundaries. In particular,
gc-10 retains the explicitly authorized plaintext annotation-export disk; it is
not suitable for application data, keys, database backups or recovery bundles.
Remote backups need their own encryption, credentials, retention and restore tests.

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

## Reprovision and restore (explicit destructive operator action)

1. Review the evaluated Disko layout for the exact host against serials and the
   recorded installed layout. Build the system on a durable reviewed checkout;
   a temporary verification checkout must never become the production source.
   Ensure trusted installation media can unlock the restored system and verify
   Secure Boot signatures where enabled. Record all mountpoints and crypttab
   entries from evaluation before any destructive command.
2. On the authorized replacement disks only, run the reviewed destructive Disko
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
6. Install the already built closure onto the prepared target using the local
   NixOS install-only workflow, after reviewing `findmnt -R /mnt` and confirming
   the target serials again:

   ```sh
   nixos-install --root /mnt --system <reviewed-built-system-closure> --no-root-passwd
   ```

   This must run from the trusted installer, not the running old host. It must
   not repartition or format. Account hashes and service secrets must already
   have been restored. When migrating existing sops-nix configuration, remove
   the obsolete `operatorStorageKey.volumeKeys` entries; preserve the private age
   identity, applicationSecrets, consumers and pinned ciphertext. Data unlock keys
   are now local root-owned keyfiles, independent of SOPS installation. Do not run the general `nixos-anywhere` command with its
   default disk phase against this prepared installation. From the installed
   target run `luxnix-verify-boot-storage`; inspect every mapping, `findmnt` and
   `swapon --show`. Inspect the built initrd and EFI to confirm that neither
   secondary key contents nor private age identities were embedded.

## Acceptance, recovery and rollback limits

Cold boot with networking disconnected. Enter one root credential, confirm data
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

Remove the legacy implementation, container inventory metadata and legacy tests
only after every fleet host has verified boot-LUKS acceptance and old storage has
reached its approved retention limit. No host is marked physically migrated by
this repository change. OpenBao identity provisioning and LX-Annotate encryption
remain independent; local OpenBao storage-unlock enrollment is superseded.

## Repository verification and physical evidence

The focused source/probe lane is:

```sh
python -m pytest -q tests/test_boot_storage.py tests/test_managed_secret_storage.py tests/test_operator_storage_migration.py
nix build .#checks.x86_64-linux.boot-storage --no-link -L
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
