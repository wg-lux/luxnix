# Encrypted storage setup

New machines get a fresh LUKS2 installation. `devenv shell luxnix` shows guidance
and changes nothing. The
[current contract](https://github.com/wg-lux/luxnix/blob/main/boot-storage.yml)
holds the requirements, and the [encrypted storage map](boot-storage-map.md)
shows how the parts fit together.

| Machine | Command | Purpose |
| --- | --- | --- |
| New, or explicitly disposable | `devenv shell luxnix install --profile /absolute/host.yml` | Build the fresh installer |
| Already encrypted | `devenv shell luxnix inspect <host>` | Verify storage and administrator credentials |
| Contents must survive | `devenv shell luxnix migrate` | Encrypt the existing installation in place |

An existing machine is treated as disposable only when its profile says so.
Configuration updates to encrypted hosts use the [deployment workflow](deployment-guide.md).

## Fresh installation

Prepare a clean, durable release and a YAML profile with `schema_version: 1`,
`host`, absolute `checkout`, `hardware_uuid` and `disks`. Each disk has a by-id
`path`, its exact `serial` and `size_bytes`. Choose one:

- Empty media: `installation: fresh` with `source_retention: new-disks`.
- Approved erasure: `installation: disposable` with `source_retention: discard-approved`.

The supported layout is one GPT disk with an EFI partition and a LUKS2 Btrfs root,
unlocked by passphrase at the console. The host configuration supplies the
subvolumes. Arrays, secondary encrypted partitions, remote initrd SSH and signed
first installation need their own integration.

Preparation prints `/nix/store/.../bin/luxnix-install`. Copy its **complete store
closure** to trusted installer media; it carries the system, the Disko script and
its Python runtime, so the installer needs no checkout.

Place the evaluated account and application credentials on independent encrypted
media, in a private directory that mirrors their target paths: root-owned files
with mode 0400 or 0600. Provision application identities through their usual
workflow; the installer keeps every key that retained data needs.

From a root terminal in the live installer, with the credential media unlocked:

```sh
/bundle/bin/luxnix-install --state /recovery/install-state --credentials /custody/credentials
/bundle/bin/luxnix-install --state /recovery/install-state --credentials /custody/credentials --apply
```

The first command checks the target. The second verifies hardware and credentials,
tests the administrator password, shows the host and disk serial, and asks once for
typed erasure approval. Disko then asks for the disk passphrase; keep it
off-machine, separate from account passwords and backups.

The installer creates the encrypted storage, copies missing credentials, installs
the system and verifies the mounts. Reboot, unlock, log in, and test the
application and recovery access: that cold boot is the acceptance. Running the
command again verifies without erasing.

### Continue an interrupted fresh installation

With the original bundle, journal and credential media, from the same installer:

```sh
/bundle/bin/luxnix-install --state /recovery/install-state --credentials /custody/credentials --resume
/bundle/bin/luxnix-install --state /recovery/install-state --credentials /custody/credentials --resume --apply
```

Recovery checks the original hardware, disk and filesystem identities and the
exact bundle, keeps matching credentials, copies only missing ones, and retries
installing the same system. Conflicting credentials stop it before anything is
written. A completed journal is verified, not repeated.

After a reboot, unlock the custody media and the existing root mapping, then mount
the root subvolumes and EFI partition at `/mnt` exactly as the host profile
describes, without Disko. Recovery verifies the mounted layout against the journal.

Without a verified storage checkpoint, formatting may have stopped part-way. Keep
the journal and have an administrator inspect that disk from trusted media; a new
destructive installation is a separate, reviewed operation.

Fresh installation discards the old contents only. Keep every key, identity and
dataset still needed elsewhere. Consent to erase comes from this operation's
profile alone.

## Preserve an existing installation

The in-place converter handles the plaintext Btrfs root and independent Btrfs
data partitions. The standard setup uses two machines: your controller and the
target, on one wired network
([step by step](migration-environment.md#two-machines-the-standard-setup)). If
`luxnix migrate` stops before planning, it lists the missing configuration;
[selecting a host](boot-storage-migration.md#selecting-a-host-for-migration)
explains each item.

1. **Keep credentials safe.** Keep the original credentials, historical keys and
   independent recovery access. Conversion encrypts from now on; older plaintext
   SSD data needs a separate data-remanence review.
2. **Plan and back up.** Connect the recovery drive and run
   `devenv shell luxnix migrate` from the reviewed clean checkout as your normal
   user. Confirm the host and serials. The guide prepares custody, then updates an
   encrypted backup of this machine on the recovery drive: a consistent snapshot
   (application services pause briefly), only the changes since the last backup,
   each file verified by checksum. It then asks for the checks only you can
   confirm. Type `VERIFIED` for completed checks; Enter pauses and keeps progress.
   Saving the plan copies its exact source to
   `/recovery/luxnix-state/sources/<revision>`.
3. **Convert.** Start the RAM environment from your SSH session with
   `devenv shell migration-boot kexec --apply`, reconnect from the controller on
   port 2222 ([two-machine steps 4–6](migration-environment.md#two-machines-the-standard-setup)),
   mount the recovery drive at `/recovery`, and run:

   ```sh
   luxnix-migration run --apply
   ```

   It runs the plan's own source. Record the recovery review there if it is still
   open, confirm `ENCRYPT IN PLACE` and enter the passphrases. From the first disk
   write until installation, every reboot returns to this environment. Continue in
   the same session through access preparation, the prepared review and
   installation.
4. **Accept.** Cold boot, unlock, test login, sudo and SSH, and open old application
   data. Run `devenv shell luxnix migrate` again to record acceptance. Keep backups
   and custody.
5. **Retire.** After acceptance, preview `devenv shell luxnix retire-containers`;
   `--apply` asks for typed approval before deleting the old container files.

An interruption resumes with the same journal; see
[interrupted setup](boot-storage-migration.md#interrupted-setup). Once the disk
has started to change, the approvals that started it stay valid until installation.

`devenv shell boot-storage-setup` and `devenv tasks run boot-storage:setup` remain
available as compatibility entry points, with the same explicit approvals.

## gc-10 and independent data disks

Both fresh installation and preservation support independent Btrfs data partitions
alongside the system disk. gc-10 keeps the existing data partition directly under
LUKS2 rather than introducing a RAID array. Its deployed inventory remains
`legacy-containers` until a separately authorized migration and acceptance.

For a fresh or disposable profile, list **every** disk from the evaluated layout
with its exact by-id path, serial and byte size. A multidisk profile cannot remap
roles by list order. Erasure approval names every selected serial. After Disko,
the installer asks for each secondary disk's existing passphrase to enroll a
random unlock key on encrypted root. Interrupted installation reuses that key;
`--resume` never formats a disk again. The external Backup export disk is not
part of this selection and must not be added to the profile.

For preservation, record gc-10's measured hardware UUID and both disks' exact
by-id paths, serials and byte sizes under `boot_storage.hosts.gc-10` in
`autoconf/config.yml` if that reviewed profile is absent. Never reuse another
host's identity. Then use `devenv shell luxnix migrate`. The conversion checks source
containers and free space on each destination filesystem before beginning a new
partition, encrypts each partition in place, and copies application data into data
disk subvolumes. The chosen root recovery passphrase also opens converted data
partitions; normal boot prompts for root once and opens data with its enrolled
key. Keep backups and original containers through cold-boot, login, database,
application and recovery acceptance. Repository checks alone do not establish
physical gc-10 acceptance.
