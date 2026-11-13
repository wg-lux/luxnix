# RAM migration environment

The RAM environment is a small system that runs entirely in memory, so the root
disk can be converted while nothing uses it. Starting it changes nothing on its
own, and the existing boot generations stay.

## Two machines: the standard setup

The standard migration uses two machines on the same wired management network:

| Machine | What it is | What stays there |
| --- | --- | --- |
| **Controller** | Your administrator workstation with the LuxNix checkout, for example gc-02 | Your SSH keys, the pinned RAM `known_hosts` file, encrypted custody (`~/.lxv`) and the inventory changes |
| **Target** | The host being encrypted | Its disks, the recovery drive at `/recovery` and a clean checkout of the same reviewed commit |

Before you start:

- The host is configured for migration: see
  [selecting a host](boot-storage-migration.md#selecting-a-host-for-migration).
  `luxnix migrate` lists every missing step at once.
- Both machines reach each other over **wired** Ethernet without VPN. The RAM
  environment has no VPN, Wi-Fi or DNS, and it reuses the target's current IPv4
  address statically.
- Your administrator SSH keys are in the inventory; the RAM environment accepts
  only those, only from the controller's address.
- The recovery drive (ext4 or Btrfs) is attached to the target, on mains power.
- Someone can reach the target's screen and keyboard for the first cold boot: the
  installed system asks for the root passphrase on its boot splash, unless
  [remote SSH root unlock](boot-storage-migration.md#remote-ssh-root-unlock) is
  configured. Conversion itself needs no one at the target.

Each step names where it runs.

1. **Controller: check the configuration and the connection.**

   ```sh
   devenv tasks run autoconf:check
   devenv shell check-connectivity <host>
   ```

   Commit the reviewed configuration so the target can check out the same commit.

2. **Controller → target: open a session.** Connect over the wired management
   address, not the VPN, so the RAM environment allows the same controller
   address later:

   ```sh
   ssh admin@<target wired address>
   cd ~/luxnix && git fetch && git checkout <reviewed commit>
   git status --short    # must print nothing
   ```

3. **Target: plan, back up and review.** In that SSH session:

   ```sh
   devenv shell luxnix migrate
   ```

   It mounts the recovery drive, saves the plan, updates the encrypted backup and
   asks for the checks only you can confirm. It pauses with *Conversion runs in the
   RAM environment*. Nothing on the disk has changed yet.

4. **Target: start the RAM environment.**

   ```sh
   devenv shell migration-boot kexec            # preview; saves the settings
   devenv shell migration-boot kexec --apply
   ```

   The preview prints the saved [settings](#2-settings-file); check that
   `controller_cidr` is your controller's wired address. If your session came over
   the VPN, add `--controller-cidr <controller wired ip>/32` to both commands.
   A session that arrives on the wired network is checked: the command refuses
   an address that would lock that session out and names the right one. Over
   the VPN it cannot check, and prints `NOT VERIFIED` for an address outside the
   target's wired network.
   The second command waits for `START RAM <host>`. **Before typing it**, copy the
   new host key from a second controller terminal:

   ```sh
   mkdir -p /home/admin/migration-<host>-kexec
   scp -o HostKeyAlias=<host> -o StrictHostKeyChecking=yes \
     admin@<target wired address>:migration-<host>-kexec/known_hosts \
     /home/admin/migration-<host>-kexec/known_hosts
   ```

   Replace `<host>` with the client hostname and `<target wired address>` with
   its Ethernet IPv4 address. These paths assume the controller account is
   `admin`; use its actual home directory otherwise. `HostKeyAlias` checks the
   installed client's key against the existing hostname pin when connecting by
   IP. Verify that pin before proceeding if it is missing or mismatched.
   Copy the file from this waiting run: each invocation generates a new RAM host
   key. Do not reuse another client's file or start a second invocation.
   Before confirming, ensure a separate SSH session to the client's wired
   address succeeds from the controller. Check `ip route get <target wired address>`
   on the controller: its interface and source IPv4 must match the wired link
   and the bundle's allowed `controller_cidr`. VPN access alone does not verify
   the connection the RAM environment needs.

   Then type the phrase. The target shuts down cleanly into RAM and your session
   ends; the disks are not changed.

5. **Controller: connect to the RAM environment** after a minute or two:

   ```sh
   ssh -o UserKnownHostsFile=/home/admin/migration-<host>-kexec/known_hosts \
     -o StrictHostKeyChecking=yes -p 2222 root@<target wired address>
   ```

   A host-key mismatch means you did not reach the environment you started: stop
   and investigate.

6. **RAM environment (over SSH): convert.**

   ```sh
   luxnix-migration run --apply
   ```

   It mounts the plan's recovery drive at `/recovery` itself; unlock and mount
   an encrypted recovery drive yourself first. Before it asks for anything, it
   checks the root filesystem read-only (`btrfs check`), which can take a long
   time on a large disk. If that check fails, nothing has been changed and no
   passphrase was needed; the full report is in
   `/run/luxnix-migration/btrfs-check-<partition>.log`. That file is in RAM, so
   read it before rebooting.

   Then type `ENCRYPT IN PLACE` and the passphrases privately. The workflow runs in the
   tmux session `luxnix-migration`; after a dropped connection, reconnect as in
   step 5 and run the same command to return to it. Do the
   [prepared review](boot-storage-migration.md#prepared-review-in-the-ram-environment)
   in this session when it asks. Stay connected until installation reports the new
   boot default.

7. **Target: cold boot and unlock.** Power the target off and on, then enter the
   root passphrase on the boot splash (or over remote unlock, if configured).

8. **Controller → target: accept.** Connect to the installed host as in step 2,
   test login, sudo and application data, and run `devenv shell luxnix migrate`
   again to record acceptance. Keep backups and custody.

If kernel lockdown (usually from Secure Boot) refuses `kexec`, replace step 4 with
the [staged boot entry](#4-stage-then-arm): approve it once at the target's screen,
then continue from step 5 with the fingerprint shown there.

## One machine at its console (exception)

Use this only when no second machine can reach the target, for example **one
laptop and an external recovery drive**. Use the staged `local-console` entry.
Build the complete planned host closure and RAM bundle while the installed
system still has network access, complete the pre-conversion recovery review, and
follow steps 1–4 below. Reboot, approve the image at the laptop's screen, and use
its root shell. Ethernet and SSH are not required for this console path once the
needed artifacts and independent credentials are local.
The builder still requires network settings; for a console-only image,
`--controller-cidr 127.0.0.1/32` prevents remote SSH access. Choose an existing
interface with `--interface` if route discovery is ambiguous.

Keep the recovery drive attached, mains power connected and the laptop awake.
After entering RAM, mount the recovery filesystem at `/recovery` if it is not
already mounted, then use `luxnix-migration run --apply`. After conversion, follow
the [prepared-review commands](boot-storage-migration.md#prepared-review-in-the-ram-environment)
on that same screen. Stay in RAM until the install reports the new boot default;
then cold-boot, unlock and test login locally. Do not select the old plaintext
generation after root encryption.

## Getting in

There are two ways to start the RAM environment:

| | `migration-boot kexec` (standard) | Staged boot entry |
| --- | --- | --- |
| Use when | You work from the controller | You are at the target's screen, or kexec is blocked |
| How it starts | From the running host, without a reboot ([remote start](#start-without-a-reboot-remote)) | Reboot; the firmware takes the one-shot entry ([stage it first](#4-stage-then-arm)) |
| The screen shows | Boot messages, then an access screen with the address and SSH fingerprint | Boot messages, then the approval prompt |
| At the machine | The access screen stays up; type `LOCAL TERMINAL` and press Enter for a root shell on the screen, `exit` returns to the access screen | Type `BOOT UNVERIFIED <host> <revision-prefix>`; a root shell opens on the screen |
| Over SSH | Port 2222 with the `known_hosts` file the `--apply` run wrote before switching | Port 2222 after approval, when administrator keys are configured; check the fingerprint shown on the screen |

Either way an operator at the machine can work in a terminal on its screen, also
when the network or SSH fails during a conversion. The RAM environment holds no
account passwords, so the typed phrase only prevents accidental input: anyone at
the machine can open this root shell. Keep the machine attended or in a locked
room while the RAM environment runs. The screen uses the German console layout
of the fleet; both phrases type the same on a US keyboard.

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
- Mount an independent **ext4 or Btrfs** filesystem at `/recovery`, at its root. The
  migration state needs file permissions, so FAT and exFAT cannot hold it. This is
  the recovery drive only; the host's own `supportedFilesystems` (for example `nfs`)
  lists kernel drivers and is unrelated.
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
| `recovery_uuid`, `recovery_fstype` | The filesystem mounted at `/recovery` (`--recovery` for another mount) | ext4 or Btrfs, at the drive's root |
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
connect over SSH. Then run:

```sh
luxnix-migration run --apply
```

It mounts the plan's recovery drive at `/recovery` when nothing is mounted
there. Images built before 2026-11-13 need `mkdir -p /recovery` and
`mount -o nosuid,nodev /dev/disk/by-uuid/<recovery-uuid> /recovery` first.

At **Access is prepared**, pause for the
[prepared review](boot-storage-migration.md#prepared-review-in-the-ram-environment).
It gives the exact commands and expected results for all four assessments; `lsblk`
alone does not verify the boot artifacts, recovery credential or password receipt.

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

## Attended RAM boot and display acceptance

Test the RAM environment on the selected running host before using it for storage
work. Keep the controller on a different running computer and an operator at the
target's physical screen. A kexec switch stops the current system and disconnects
its SSH sessions; it does not test the installed generation's firmware boot or
root-unlock path.

Before `--apply`, verify the exact host and immutable bundle, the wired interface
and source address, and that the controller's SSH identity is allowed by the
bundle. Copy and pin the newly generated `known_hosts` file while the command
waits for the typed phrase. Verify the existing disk passphrase privately so the
operator can recover the unchanged installed system if RAM networking or display
fails. No migration or encryption command is part of this boot-only test.

After the switch, require both observations:

- The physical screen shows the **LuxNix migration environment** banner with the
  selected host, management address and host-key fingerprint. A working SSH
  connection does not prove that the display is visible.
- The controller reconnects with strict host-key checking and verifies the
  expected `-migration` hostname, `tmpfs` root, admitted RAM environment and
  unchanged target storage. Do not mount target filesystems or run migration.

Record screen visibility separately from network access. If the display stays
black, record the test as failed even if SSH works; inspect DRM/framebuffer and
console logs through that verified SSH connection. If networking fails as well,
the console operator can restart into the unchanged installed system and enter
its disk passphrase. Never reboot both the target and its only jump/controller
host together.

The `migration-kexec` VM check switches from its running system into RAM, asserts
readable screen text through OCR and saves `migration-kexec-visible-console.png`.
This catches a blank emulated screen; actual GPU, monitor and cable behaviour
still requires the physical observation above.

## Prepare and start through luxnix

Run these commands on the controller; no Nix store path needs to be copied or
typed:

```sh
devenv shell luxnix ram push gc-09 --settings /path/to/reviewed-settings.yml
devenv shell luxnix ram gc-09
devenv shell luxnix ram gc-09 --apply
```

The first push saves the reviewed settings privately on the controller. Later
pushes can use `luxnix ram push gc-09` without the settings argument. Settings use
the existing migration-boot schema; they cannot select executable code. The
host's durable checkout must be clean and match the controller's selected Git
HEAD. Uncommitted controller edits are not packaged as a RAM release.

Push sends the small operator helper and settings over host-key-checked SSH,
then builds the RAM bundle on the host using its normal Nix trust rules. It does
not import unsigned controller paths, relax signature checks, modify the host
checkout, change boot entries or start RAM. Successful preparation saves private
receipts binding the host, release revision and artifact hashes.

The start command verifies those receipts and the pushed helper before invoking
the existing `migration-boot kexec` workflow in an interactive SSH terminal.
Without `--apply` it is a preview. With `--apply`, sudo and the `START RAM` phrase
remain mandatory. Enter passwords only in the terminal. While the command waits
at that phrase, copy its freshly generated `known_hosts` file to the controller
and pin it **before** confirming. Every run creates a different identity: do not
start a second copy while the first one waits.

Once the same CLI is available locally on a prepared target, `luxnix ram --apply`
uses that target's saved receipt. No command here authorizes storage migration.

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

Before anything runs from it, the RAM environment compares its store image in
memory with the digest in the bundle. If they differ, the screen says so and the
machine restarts into the installed system after 15 seconds; no disk was
changed, so start again. A crash of the RAM kernel also restarts the machine
after 15 seconds instead of hanging; its report is kept in
`/var/lib/systemd/pstore` on the installed system. If starts keep failing this
way on one machine, use the [staged boot entry](#4-stage-then-arm): a firmware
restart resets all hardware, which a switch from the running system does not.

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
