# Boot storage recovery

Use this page when a host stops in emergency mode after a storage change, a
rebuild is refused by the root-storage preflight, or a migration was interrupted.
Classifying and previewing only read. `restore --apply` changes the system profile
and boot entries; resuming encryption continues the migration. Recovery keeps the
existing data and keys.

## Build recovery media first

Build this before migrating and keep it with the recovery drive:

```bash
nix build .#luxnix-recovery-iso
```

The image holds only storage tools and `luxnix-boot-recover`, so it works whatever
the state of application builds. Boot it on the affected machine.

## Identify the disk state

The partition itself is the proof of its state:

```bash
luxnix-boot-recover classify --partition /dev/disk/by-partlabel/nixos_root
```

Use the root partition named in the host profile or migration plan; the label above
is an example. This only reads and is safe to repeat. On a running host,
`devenv shell luxnix recover --partition <path>` prints the same procedure.

| State | Bootable generations | Next step |
| --- | --- | --- |
| `plaintext` | Those that mount the partition directly | [Select a generation](#select-a-matching-generation) |
| `encrypting` | None until encryption finishes | [Resume encryption](#resume-interrupted-encryption) |
| `encrypted` | Those that mount `/dev/mapper/cryptroot` | Unlock, then [select a generation](#select-a-matching-generation) |
| `unknown` | None | [Unrecognized partition](#unrecognized-partition) |

Selection proceeds only when every probe succeeds and the layout matches; a cold
boot then confirms the choice.

## Select a matching generation

On an encrypted disk, unlock first:

```bash
cryptsetup open --type luks2 /dev/disk/by-partlabel/nixos_root cryptroot
```

Mount the root subvolumes and the EFI partition, from the mapper device when
encrypted or the partition when plaintext:

```bash
device=/dev/mapper/cryptroot    # or /dev/disk/by-partlabel/nixos_root
mount -o subvol=root "$device" /mnt
mount -o subvol=nix "$device" /mnt/nix
mount -o subvol=home "$device" /mnt/home
mount -o subvol=persist "$device" /mnt/persist
mount -o subvol=log "$device" /mnt/var/log
mount /dev/disk/by-partlabel/boot /mnt/boot
```

List the generations, preview a choice, then add `--apply` to select it:

```bash
luxnix-boot-recover generations --root /mnt
luxnix-boot-recover restore --root /mnt --generation <N>
```

`restore` accepts only generations that match the disk and changes only the system
profile and boot entries. Reboot when it finishes.

## Resume interrupted encryption

The LUKS2 header keeps the progress; leave the partition as it is. Boot the staged
LuxNix migration entry (the boot default already points there) and run in its root
terminal:

```bash
luxnix-migration run --apply
```

To accept a layout an administrator has already reviewed, use
`luxnix-migration recover --assessor <name> --apply`.

## When the RAM environment has a black screen

The RAM environment is the minimal NixOS profile with a compressed read-only
store; it loads no desktop, applications or host closure, and the loader checks
memory before copying. It boots with basic graphics (`nomodeset`), visible kernel
messages, and the selected console last, so on `tty1` errors and the approval
prompt appear on the attached screen (a `ttyS0` build uses the serial console).

A blank screen alone does not mean RAM ran out. Follow
[If the screen stays black](migration-environment.md#if-the-screen-stays-black):
switch to the first console, rebuild images made before the console fix, and use
SSH after a remote start. Keep the existing system and recovery entries, and
report whether the screen went blank before or after the first kernel messages.
The UEFI VM test covers boot and keyboard approval with 5 GiB RAM; each physical
display is confirmed on the host.

## Unrecognized partition

Compare the partition with the disk identity in the migration plan, keep the disk
unchanged, and take a full-disk image before any repair. Restore a LUKS2 header
backup only to the exact partition the plan names.

## When a rebuild is refused

The preflight runs on the host for `nixos-rebuild switch`, `boot`, `test` and
`dry-activate`, `nho`, `nhb`, Ansible, `luxnix-safe-activate` and `nixos-install`.
A refusal names each cause, leaves disks and boot entries as they were, and removes
the refused generation from the boot menu. Compare at any time (read-only):

```bash
luxnix-root-preflight status
```

| Code | Meaning | Fix |
| --- | --- | --- |
| `root-not-luks` | Configuration expects encryption; the disk is plaintext | Keep `legacy-containers` until `devenv shell luxnix migrate` finishes |
| `root-is-luks` | Configuration expects plaintext; the disk is encrypted | Select `boot-luks` for this host |
| `root-reencrypting` | Encryption is still in progress | [Resume encryption](#resume-interrupted-encryption) |
| `mapping-missing`, `mapping-identity` | `cryptroot` is closed or backed by another device | Boot the matching generation and check the disk |
| `partition-identity`, `disk-missing`, `partition-missing` | The partition is not on the declared disk | Check the host's disk facts against the real hardware |
| `luks-uuid` | The header differs from the pinned UUID | Treat it as a replaced disk or header until confirmed |
| `mount-*`, `subvolume` | Mounts differ from the configuration | Align the layout and the configuration |
| `recovery-credential` | No tested passphrase matches this header | Run `sudo luxnix-setup-boot-password` (repeatable) |
| `esp-capacity`, `esp` | The EFI partition lacks space for this generation | Remove old generations |
| `no-fallback-generation` | No other boot entry matches this disk | Boot a matching generation first, or keep recovery media ready and use an override |

### Audited override

Physical mismatches always stop. For other findings, an administrator at a root
terminal can allow one activation of one exact system:

```bash
sudo luxnix-root-preflight override --system <closure> --operator <name> --reason <text>
```

The override lasts 15 minutes, is used once, and is recorded in
`/var/lib/luxnix/root-guard-audit.jsonl` and the system journal.

The preflight also runs when `NIXOS_NO_CHECK=1` is set: `sudo` drops the variable,
and `switch-to-configuration` checks and logs its use itself. Root can still write
the EFI partition directly, so root access remains the trust boundary.

## After encryption

Once `devenv shell luxnix verify` passes and the host has cold-booted, set
`boot-luks` and pin the UUID that `verify` reports, in
`ansible/inventory/host_vars/<host>.yml`, then regenerate:

```yaml
host_luxnix:
  storage.operatorUnlocked.layout: '"boot-luks"'
  storage.operatorUnlocked.rootIdentity.luksUUID: '"<uuid>"'
```

Plaintext generations stay in the boot menu without booting the encrypted disk.
Generations built before the guard carry no `root-storage.json`; recover them
manually with this page.

## What the fallback check proves

For systemd-boot it confirms an entry's kernel and initrd exist and that the entry
boots its generation. For Secure Boot images it confirms the file name, because
the image is signed as one file. A cold boot on the machine is the final proof.
