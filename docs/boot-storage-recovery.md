# Boot storage recovery

Use this page when a host stops in emergency mode after a storage change, when a
rebuild is refused by the root-storage preflight, or when a migration was
interrupted. Classification and preview commands are read-only. Selecting a
generation with `restore --apply` changes the system profile and boot entries.
Resuming interrupted encryption uses the migration workflow and writes storage;
none of these recovery paths authorizes formatting or replacement keys.

## Build recovery media first

Build this before starting a migration, and keep it with the recovery drive:

```bash
nix build .#luxnix-recovery-iso
```

The image holds only storage tools and `luxnix-boot-recover`. It contains no host
closure or application package, so a broken application build cannot block
recovery. Boot it on the affected machine.

## Identify the disk state

Read the state from the partition itself. A saved migration stage never proves
what is on the disk.

```bash
luxnix-boot-recover classify --partition /dev/disk/by-partlabel/nixos_root
```

Use the exact root partition from the prepared host profile or migration plan;
the partition label above is only an example, not proof of disk identity.

This changes nothing and is safe to repeat. On a running host,
`devenv shell luxnix recover --partition <path>` prints the same procedure.

| State | Compatible root layouts | What to do |
| --- | --- | --- |
| `plaintext` | Only those that mount the partition directly | [Select a generation](#select-a-matching-generation) |
| `encrypting` | None | [Resume encryption](#resume-interrupted-encryption) |
| `encrypted` | Only those that mount `/dev/mapper/cryptroot` | Unlock, then [select a generation](#select-a-matching-generation) |
| `unknown` | None | Stop. See [Unrecognized partition](#unrecognized-partition) |

A compatible layout does not prove a generation will boot. Missing probes,
incomplete filesystem membership and interrupted encryption cannot establish
generation compatibility; recovery selection stops on that uncertainty.

A plaintext-root generation does not boot after encryption, and an encrypted-root
generation does not boot before it. Retained boot entries of the other kind are
not a fallback.

## Select a matching generation

For an encrypted disk, unlock it first:

```bash
cryptsetup open --type luks2 /dev/disk/by-partlabel/nixos_root cryptroot
```

Mount the root subvolumes and the EFI partition. Use the mapper device on an
encrypted disk and the partition on a plaintext disk:

```bash
device=/dev/mapper/cryptroot    # or /dev/disk/by-partlabel/nixos_root
mount -o subvol=root "$device" /mnt
mount -o subvol=nix "$device" /mnt/nix
mount -o subvol=home "$device" /mnt/home
mount -o subvol=persist "$device" /mnt/persist
mount -o subvol=log "$device" /mnt/var/log
mount /dev/disk/by-partlabel/boot /mnt/boot
```

List the generations, then preview your choice:

```bash
luxnix-boot-recover generations --root /mnt
luxnix-boot-recover restore --root /mnt --generation <N>
```

`restore` refuses a generation that does not match the disk. Add `--apply` to
select it. That changes the system profile and boot entries only. Reboot when it
finishes.

## Resume interrupted encryption

Do not format the partition and do not run a filesystem repair on it. Boot the
tested installer, mount the recovery drive at `/recovery`, and rerun:

```bash
devenv shell luxnix migrate
```

The conversion resumes from the LUKS2 header. To accept a layout that an
administrator has already reviewed instead, use
`devenv shell luxnix recover --assessor <name> --apply`.

## Unrecognized partition

Compare the partition with the disk identity saved in the migration plan. Restore
a LUKS2 header backup only if the plan names this exact partition. Until then,
leave the disk unchanged, and take a full-disk image before any repair attempt.

## When a rebuild is refused

The preflight runs on the target host for `nixos-rebuild switch`, `boot`, `test`
and `dry-activate`, the `nho` and `nhb` aliases, Ansible, `luxnix-safe-activate`
and `nixos-install`. A refusal names each cause and changes no disk or boot entry.
A refused generation is removed from the system profile so it cannot occupy a boot
menu slot.

Read the current comparison at any time; it is safe to repeat:

```bash
luxnix-root-preflight status
```

| Code | Meaning | Fix |
| --- | --- | --- |
| `root-not-luks` | The configuration needs encrypted root; the disk is plaintext | Keep `legacy-containers` until `devenv shell luxnix migrate` finishes |
| `root-is-luks` | The configuration mounts plaintext root; the disk is encrypted | Select `boot-luks` for this host |
| `root-reencrypting` | Encryption has not finished | [Resume encryption](#resume-interrupted-encryption) |
| `mapping-missing`, `mapping-identity` | `cryptroot` is closed or backed by another device | Boot the correct generation and check the disk |
| `partition-identity`, `disk-missing`, `partition-missing` | The partition is not on the declared disk | Check the host's disk facts; do not edit them to match an unknown disk |
| `luks-uuid` | The header differs from the pinned UUID | Treat as a replaced disk or header until proven otherwise |
| `mount-*`, `subvolume` | Mounts differ from the configuration | Correct the layout or the configuration |
| `recovery-credential` | No tested passphrase matches this header | Run `sudo luxnix-setup-boot-password` (safe to repeat) |
| `esp-capacity`, `esp` | The EFI partition cannot hold this generation | Remove old generations |
| `no-fallback-generation` | No other usable boot entry matches this disk | Reboot into a matching generation first, or keep recovery media ready and use an override |

### Audited override

Findings marked `physical mismatch` cannot be overridden. For the others, an
administrator at a root terminal can allow one activation of one exact closure:

```bash
sudo luxnix-root-preflight override --system <closure> --operator <name> --reason <text>
```

The override expires after 15 minutes and is consumed by its first use. It is
recorded in `/var/lib/luxnix/root-guard-audit.jsonl` and the system journal.

`NIXOS_NO_CHECK=1` does not skip this check: `sudo` no longer forwards it, and
`switch-to-configuration` runs the preflight itself when it is set and records the
use in the audit log. It still skips unrelated upstream checks. A root user can
always write to the EFI partition directly, so root access remains the trust
boundary.

## After encryption

Once `devenv shell luxnix verify` passes and the host has cold-booted, change the
host to `boot-luks` in its inventory and regenerate. Pin the UUID that `verify`
reports in the same change, as host facts in
`ansible/inventory/host_vars/<host>.yml`:

```yaml
host_luxnix:
  storage.operatorUnlocked.layout: '"boot-luks"'
  storage.operatorUnlocked.rootIdentity.luksUUID: '"<uuid>"'
```

After conversion, the retained plaintext generations stay in the boot menu but
cannot boot. Generations built before this guard have no `root-storage.json`, so
automatic detached rollback refuses them; manual recovery from this page still
works.

## Limits of the fallback check

For systemd-boot, the check confirms that an entry's kernel and initrd exist and
that the entry boots that generation's closure. For Secure Boot images it can only
confirm the file name, because the contents are signed into one file. Neither
proves the entry will boot: only a cold boot on the real machine does.
