# RAM migration environment

A small EFI loader starts a separate runtime from the recovery drive, copies it
into RAM, verifies its digest and releases the drive. From there the root disk is
converted while nothing uses it. Booting it changes nothing on its own, and the
existing boot generations stay.

## 1. Prepare

- Use a clean, committed checkout with the reviewed revision and locked inputs.
- Know where the data backup is and how its restore was tested. A remote backup
  works; the journal, evidence, credentials and checkout still need local storage
  outside the target disks.
- Mount an independent **ext4 or FAT** filesystem at `/recovery`, at its root.
- Have systemd-boot, enough `/boot` space, and physical console or BMC access.
  The target needs Python 3.12+, `objcopy`, `sbverify`, `bootctl`, `findmnt`,
  `lsblk` and `blkid`.

## 2. Settings file

The settings file describes how the RAM environment reaches the network and finds
the recovery drive. It is written only when you run `migration-boot discover`;
`build` and `kexec` only read it. Create it on the **target host**, outside the
checkout:

1. Mount the recovery drive at `/recovery` and connect the wired network the
   RAM environment will use.
2. Run discovery with your controller's address, as the target sees it:

   ```sh
   devenv shell migration-boot discover --controller-cidr <controller-ip>/32 \
     > ~/migration-settings.yml
   ```

3. Review each value against the table below, then pass the file to `build` or
   `kexec` with `--settings ~/migration-settings.yml`.

| Key | Where discovery gets it | What to check |
| --- | --- | --- |
| `host` | This machine's hostname | It names the host in `autoconf/config.yml` |
| `hardware_uuid` | `boot_storage.hosts.<host>.hardware_uuid` in `autoconf/config.yml` | It equals `sudo cat /sys/class/dmi/id/product_uuid` |
| `interface` | The interface of the default route (`--interface` to choose) | A wired interface; the RAM environment has no Wi-Fi |
| `address` | That interface's IPv4 address and prefix (`--address`) | A stable address: the RAM environment uses it statically |
| `gateway` | The default route's gateway (`--gateway`), or `null` | Needed only when the controller is on another subnet |
| `controller_cidr` | Only `--controller-cidr` | The address SSH may come from, usually one `/32` |
| `recovery_uuid`, `recovery_fstype` | The filesystem mounted at `/recovery` (`--recovery` for another mount) | ext4 or FAT, at the drive's root |
| `recovery_luks_uuid` | The LUKS layer below that filesystem, or `null` | Present when the recovery drive is encrypted |

When reading the file, `build` and `kexec` require exactly these keys, with
`host` and `hardware_uuid` matching the inventory and every value a string or
`null`. A flag such as `--address` overrides one value for that run. A missing
value stops the command and names the flag to supply. Run discovery again whenever
the network, the controller or the recovery drive changes; the file may be copied
to a build controller unchanged.

`migration-boot discover --controller-cidr <ip>/32 --format command` prints the
complete, quoted `build` command instead of YAML.

## 3. Build

```sh
devenv shell migration-boot build gc-09 --settings ~/migration-settings.yml \
  --output ~/migration-gc-09
```

Use a reachable management network; the image has no VPN, DNS or Wi-Fi of the
host. Without administrator SSH keys, a local-console image disables SSH and the
physical root terminal still works. Limits live in `conf/migration-environment.yml`.

For encrypted recovery media, add `--recovery-luks-uuid <uuid>`; its password is
entered at the console during boot. The image holds no private key or password.

Keep `migration.efi`, `migration.squashfs`, `manifest.json` and the reported EFI
SHA256. In local-console mode the digest detects payload corruption; the loader
itself is not authenticated by firmware, so the physical approval prompt is the
trust step. For firmware authentication, build with `--boot-trust secure-boot
--sign` using [fleet signing custody](secure-boot.md); that needs Secure Boot with
the fleet certificate enrolled, and administrator SSH keys.

## 4. Stage, then arm

On the target, as your normal user in the devenv shell:

```sh
migration-boot stage gc-09 --allow-unverified-boot
migration-boot stage gc-09 --allow-unverified-boot --apply
```

The first command verifies; the second publishes the image and arms it for the
next boot only, asking for sudo itself. It finds the bundle in `~/migration-<host>`
(`--bundle <directory>` for another), checks identities and payloads, and leaves
the normal boot default unchanged.

From the controller, after `devenv shell check-connectivity <host>`:

```text
devenv shell stage-migration-boot --limit <host> \
  -e migration_image=<absolute-migration.efi> -e migration_sha256=<digest> \
  -e migration_payload=<absolute-migration.squashfs> \
  -e migration_allow_unverified_boot=true
```

This copies and verifies the artifacts. Review the result, then repeat with
`-e migration_apply=true` to publish and arm. Secure Boot images omit
`migration_allow_unverified_boot`; another recovery mount uses
`-e migration_recovery=<mountpoint>`.

## 5. Boot and migrate

After the reboot, the physical screen (`tty1`, or `ttyS0` when built with
`--console ttyS0`) asks for `BOOT UNVERIFIED <host> <revision-prefix>`. Check the
host and trust notice, then type the phrase to open a root terminal and, with
keys configured, SSH on port **2222**. Verify the SSH fingerprint on the console
and pin it before connecting with strict host-key checking; it changes each boot.

Mount the recovery drive at `/recovery` and run:

```sh
luxnix-migration run --apply
```

`luxnix-migration` finds this host's saved plan, checks the plan's source copy in
`/recovery/luxnix-state/sources/<revision>` against its revision and `flake.lock`,
and runs that source. A plan from a newer commit therefore needs no new image.
Afterwards, files created as root are handed back to the plan's operator, so the
installed host continues as that user. The steps follow the
[migration reference](boot-storage-migration.md).

The environment keeps the conversion running safely:

- Conversion starts on mains power; on battery alone it asks to connect power.
- Sleep and hibernation are disabled, and the lid, suspend key and idle are ignored.
- Over SSH it runs in the tmux session `luxnix-migration`. After a dropped
  connection, run the same command to return to it.
- One workflow runs at a time.

Just before the first disk write, the boot default moves to the migration entry
this environment started from, so every reboot returns here (still behind console
approval). Installation then clears that override, `loader.conf` selects the new
encrypted generation, and the install verifies it boots the planned system. If
nothing on the disk changed, the previous default returns. Started from another
entry, the environment warns instead; then stay in the session until installation
reports the new default.

Keep recovery material until cold boot, unlock, administrator login and
LX-Annotate data access all pass. After conversion, the old generation stays in the
menu but only the encrypted generation boots.

## Start without a reboot (remote)

For remote work, build and start the RAM environment directly from the running
host, with no reboot, boot entry or console. Over your existing SSH session, from
the devenv shell on the **target host**:

```sh
devenv shell migration-boot kexec --settings ~/migration-settings.yml
devenv shell migration-boot kexec --settings ~/migration-settings.yml --apply
```

The first command builds the RAM environment from the reviewed checkout and
creates the SSH host key it will use. It prints that key's fingerprint and writes
a ready `known_hosts` file to `~/migration-<host>-kexec/`; nothing is loaded. Copy
that file to your controller.

The second command asks you to type `START RAM <host>`, loads the RAM
environment, and switches to it through `systemctl kexec`: the host shuts down
cleanly, and the disks stay as they are. Your connection ends; reconnect with the
printed command:

```sh
ssh -o UserKnownHostsFile=<known_hosts> -o StrictHostKeyChecking=yes -p 2222 root@<address>
```

The running host is the trust step: you start the environment as root from a
verified session, so no console phrase is needed. Remote access stays narrow:

- SSH listens on port 2222 only, for `controller_cidr` only, with the
  administrator keys from the inventory.
- The host key is created on the host before the switch and handed over in the
  initrd; the environment opens SSH only with that exact key, so the fingerprint
  you pinned is the one you reach.
- The management interface keeps its name, matched by its permanent hardware
  address.

It needs the reviewed settings with `controller_cidr`, a wired interface with its
permanent address, and free memory for the image. Kernel lockdown, usually from
Secure Boot, blocks unsigned images; such hosts use the staged boot entry instead.
`--bundle <path>` starts a prebuilt bundle. A later reboot returns to the boot
default, which [during conversion](boot-storage-map.md#the-boot-default-during-conversion)
is the staged migration entry.

## Developer checks

Build a disposable console fixture with
`LUXNIX_MIGRATION_LOCAL_CONSOLE=1 uv run python -m tests.test_migration_loader_vm`,
set `LUXNIX_MIGRATION_BUNDLE` to its output and `LUXNIX_QEMU` to QEMU, then run
`uv run pytest -q tests/test_migration_loader_vm.py`. This needs KVM, mtools,
dosfstools, binutils, OpenSSL and sbsigntool.

VM tests cover RAM startup, console approval, tamper rejection, the boot default
across power cuts (`boot-default-hold`) and the remote start without reboot with a
pinned host key (`migration-kexec`). Firmware trust, networking,
encrypted recovery media and installation acceptance are confirmed on the host.
