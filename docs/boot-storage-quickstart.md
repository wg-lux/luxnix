# Encrypted storage setup

Fresh LUKS2 installation is the default for new machines. Run
`devenv shell luxnix` for setup guidance; it changes nothing.
`devenv shell luxnix --profile /absolute/host.yml` is shorthand for fresh
installer preparation. The
[current contract](https://github.com/wg-lux/luxnix/blob/main/boot-storage.yml)
is the single requirements source. Existing machines are never automatically
reclassified as disposable.

| Machine | Command | Purpose |
| --- | --- | --- |
| New or explicitly disposable | `devenv shell luxnix install --profile /absolute/host.yml` | Build the fresh installer. |
| Already encrypted | `devenv shell luxnix inspect gc-02` | Verify actual storage and administrator credentials. |
| Existing contents must survive | `devenv shell luxnix migrate` | Preserve and encrypt the existing installation. |

Replace example hosts and paths with the administrator's prepared values.
Configuration updates to an encrypted host use the [deployment workflow](deployment-guide.md).

## Fresh installation

An administrator prepares a clean, durable release and a YAML profile containing
`schema_version: 1`, `host`, absolute `checkout`, `hardware_uuid` and `disks`.
Each disk has a stable by-id `path`, exact `serial` and `size_bytes`. Use
`installation: fresh` with `source_retention: new-disks` for empty media, or
`installation: disposable` with `source_retention: discard-approved` for erasure
explicitly authorized for this operation.

The supported profile is one GPT disk, an EFI partition and LUKS2/Btrfs root
with console passphrase unlock. The host configuration supplies subvolumes.
Arrays, secondary encrypted partitions, remote initrd SSH and signed first
installation require separate integration; do not disable security controls to
fit this profile.

Preparation prints `/nix/store/.../bin/luxnix-install`. The bundle contains the
matching system closure, Disko script and Python runtime. The administrator
retains and copies its **complete Nix store closure** to trusted installer media;
copying just the executable is insufficient. Running it needs no checkout or
separate Python environment.

Prepare the evaluated account and application credentials on independent
encrypted media, in a private directory mirroring their absolute target paths.
Files must be root-owned mode 0400 or 0600; directories must be private. Provision
required application identities through their existing administrative workflow.
The installer never replaces keys needed by retained data.

From a root terminal in the live installer, with the credential media unlocked:

```sh
/bundle/bin/luxnix-install --state /recovery/install-state --credentials /custody/credentials
/bundle/bin/luxnix-install --state /recovery/install-state --credentials /custody/credentials --apply
```

Replace `/bundle` with the prepared store path. The first command checks the
target only. The second verifies hardware and credentials, tests the administrator
password, displays the host and disk serial, and requests one typed erasure
approval. Disko asks for and confirms the disk passphrase. Keep it off-machine
for recovery; it is separate from account passwords and data backups.

The installer creates encrypted storage, copies credentials without overwriting,
installs the matching system and verifies actual mounts. Reboot, unlock and log
in; then test application initialization and recovery access. Pre-reboot success
is explicitly **awaiting cold-boot acceptance**. Repeating the command refuses
another erase.

### Continue an interrupted fresh installation

Keep the original bundle, journal and provisioning media. From the same trusted
installer, preview recovery and then continue explicitly:

```sh
/bundle/bin/luxnix-install --state /recovery/install-state --credentials /custody/credentials --resume
/bundle/bin/luxnix-install --state /recovery/install-state --credentials /custody/credentials --resume --apply
```

Recovery requires the original hardware and disk identities, the exact bundle,
and the filesystem identities recorded after storage creation. It never runs
Disko. It checks all already-copied credentials against the provisioning media,
keeps matching files, copies only missing files, then retries installation of the
same closure. Conflicting credentials stop recovery before any missing file is
written. A completed journal is verified without repeating installation; physical
cold-boot acceptance remains separate.

After a reboot, unlock custody and the **existing** root LUKS mapping, then remount
the root subvolumes and EFI partition at `/mnt` using the devices, filesystem
types and subvolume options in the administrator's prepared host profile. Do not
run Disko to mount them. The recovery command verifies the complete mounted layout
against the journal; a missing or changed mount stops it. A process interruption
normally leaves these mounts in place.

If no verified storage checkpoint exists, formatting may have stopped part-way.
`--resume` refuses to infer success from partition labels or an open mapping.
Preserve the journal and have an administrator inspect that exact selected disk
from trusted media. This state cannot authorize another erase or an automatic
repair; any new destructive installation needs a separate reviewed operation.

Fresh installation does not require restoring intentionally discarded contents.
It does require preserving any data, application keys or identities still needed
elsewhere. An old migration plan or historical approval is never erase consent.

## Preserve an existing installation

Use the [migration reference](boot-storage-migration.md) when contents must
survive. Only one plaintext Btrfs root is supported by the in-place converter;
unsupported layouts stop without a formatting fallback.

1. Make and test a backup. Preserve original credentials, historical keys and
   independent recovery access. Conversion is not secure erasure of old plaintext
   SSD data; prior patient data requires a separate data-remanence review.
2. Connect recovery media and run `devenv shell luxnix migrate` from the reviewed
   clean checkout as the normal user. Confirm the displayed host and serials.
   The guide prepares custody, checks copies and asks only for human evidence.
   Type `VERIFIED` only for completed checks; Enter pauses without losing state.
3. Boot trusted installer media and mount recovery at `/recovery`. Keep the
   pinned checkout, Nix artifacts and Python environment independently available.
   State must be root-owned and private; disable swap. From the preserved checkout:

   ```sh
   python -m lx_administration.storage.boot_setup run --apply
   ```

   Confirm `ENCRYPT IN PLACE`, provide the passphrases and follow the requested
   prepared-stage review and separate install confirmation. Do not run `sudo devenv`.
4. Cold boot, unlock, test login/sudo/SSH and decrypt old application data. Rerun
   `devenv shell luxnix migrate` to record acceptance. Keep backups and custody.
5. Only after acceptance, preview `devenv shell luxnix retire-containers`.
   Adding `--apply` requests typed approval to delete the retired container files.

For interruptions, follow [recovery](boot-storage-migration.md#interrupted-setup)
with the same journal. A rebuild cannot encrypt plaintext root, and an older
plaintext boot generation cannot open the converted root.

Administrators retain `devenv shell boot-storage-setup` and
`devenv tasks run boot-storage:setup` as compatibility entry points. Their actions
remain explicit; setup guidance itself does not authorize disk changes.
