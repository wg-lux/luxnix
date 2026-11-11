# RAM migration environment

The RAM environment is a small system that runs entirely in memory, so the root
disk can be converted while nothing uses it. Starting it changes nothing on its
own, and the existing boot generations stay.

## Getting in

There are two ways to start it. Choose by where you are:

| | Staged boot entry | `migration-boot kexec` |
| --- | --- | --- |
| Use when | You are at the machine | You work remotely |
| How it starts | Reboot; the firmware takes the one-shot entry ([stage it first](#4-stage-then-arm)) | From the running host, without a reboot ([remote start](#start-without-a-reboot-remote)) |
| The screen shows | Boot messages, then the approval prompt | Boot messages, then an access screen with the address and SSH fingerprint |
| At the machine | Type `BOOT UNVERIFIED <host> <revision-prefix>`; a root shell opens on the screen | No login; the screen only shows how to connect |
| Over SSH | Port 2222 after approval, when administrator keys are configured; check the fingerprint shown on the screen | Port 2222 with the `known_hosts` file the `--apply` run wrote before switching |

Connect from the controller (an address in `controller_cidr`) with:

```sh
ssh -o UserKnownHostsFile=<known_hosts> -o StrictHostKeyChecking=yes -p 2222 root@<address>
```

For the staged entry, write `known_hosts` yourself from the fingerprint on the
screen; it changes with every boot. Then continue with
[luxnix-migration](#5-boot-and-migrate).

### If the screen stays black

Starting takes a minute or two while the image is copied and unpacked. If the
screen is still black after that:

1. **Switch to the first console:** press `Ctrl`+`Alt`+`F1`; the prompt and
   messages appear there.
2. **Check the image's age:** images built before the console fix sent the
   prompt to the serial port, not the screen. The `gc-09` image built from
   `b716c024` is one of them. Build and stage a new image from the current checkout.
3. **Check the build option:** an image built with `--console ttyS0` uses the
   serial port by design. Build with the default `--console tty1` for a screen.
4. **After a kexec start, use SSH:** the screen is not needed; connect as above.

To leave a black staged boot, power off and on: the migration entry is armed for
one boot only, so the normal system starts again, as long as conversion has not
begun. Once it has begun, every reboot returns to the migration entry by design;
see [the boot default during conversion](boot-storage-map.md#the-boot-default-during-conversion).
Report where the screen went black, before or after the first kernel messages,
so the cause can be found.

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

The settings tell the RAM environment how to reach the network and find the
recovery drive. They live with the plan, in
`/recovery/luxnix-state/<host>/migration-settings.yml`, so `build` and `kexec`
need no path:

1. Run `devenv shell luxnix migrate` first, so the plan's state directory exists.
2. Keep the recovery drive mounted at `/recovery` and the wired network connected.
3. Run `build` or `kexec` on the **target host** without `--settings`. On first
   use they discover the values below, save them with the plan (mode 0600) and
   print them; later runs reuse that file.

The controller address comes from your SSH session when it arrives over the
management network. Over a VPN or from the local console, add
`--controller-cidr <controller wired ip>/32`; the RAM environment has no VPN.
To start over, move the saved file aside and run again. `--settings <file>` uses
another file, and a flag such as `--address` overrides one value for one run.

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

A settings file must hold exactly these keys, with `host` and `hardware_uuid`
matching the inventory. An empty or older file stops with the keys it lacks or
should not have; move it aside and run again to rediscover.
`migration-boot discover` prints the same values as YAML without saving them.

## 3. Build

```sh
devenv shell migration-boot build gc-09 --output ~/migration-gc-09
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

Get in as described in [Getting in](#getting-in): approve at the screen, or
connect over SSH. Then mount the recovery drive and run:

```sh
mkdir -p /recovery    # images built before 2026-11-11 lack this directory
mount -o nosuid,nodev /dev/disk/by-uuid/<recovery-uuid> /recovery
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
  connection, run the same command to return to it. When the workflow ends, the
  window shows its result and closes after you press Enter.
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
devenv shell migration-boot kexec
devenv shell migration-boot kexec --apply
```

The first command builds the RAM environment from the reviewed checkout and shows
what it will do; nothing is loaded. The second builds the same, creates the SSH
host key the RAM environment will use, writes it to
`~/migration-<host>-kexec/known_hosts` and waits for `START RAM <host>`. Each run
creates a new key, so copy that file to your controller **while the second command
waits**, then type the phrase. It loads the RAM environment and switches through
`systemctl kexec`: the host shuts down cleanly, and the disks stay as they are.
Your connection ends; after a minute or two, reconnect with the printed command.
The machine's screen shows the address, the allowed controller and the
fingerprint, or says that SSH stayed closed if the key did not arrive.

Run both commands in an interactive terminal as your normal user (not `sudo -i`):
they need your private runtime directory and ask for the phrase and for `sudo`.
The image is about 430 MB and fits there on machines with 16 GB.

The running host is the trust step: you start the environment as root from a
verified session, so no console phrase is needed. Remote access stays narrow:

- SSH listens on port 2222 only, for `controller_cidr` only, with the
  administrator keys from the inventory.
- The host key is created on the host before the switch and handed over in the
  initrd; the environment opens SSH only with that exact key, so the fingerprint
  you pinned is the one you reach.
- The management interface keeps its name, matched by its permanent hardware
  address.

It needs the plan's settings, a wired interface with its
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
