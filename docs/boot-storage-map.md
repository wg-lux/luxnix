# Encrypted storage map

An overview of encrypted root storage: the parts, how they connect, and which page
to open. Requirements live in the
[current contract](https://github.com/wg-lux/luxnix/blob/main/boot-storage.yml).

## Which page do I need?

| Situation | Start here |
| --- | --- |
| New machine, or contents may be erased | [Fresh installation](boot-storage-quickstart.md#fresh-installation) |
| Already encrypted; check it | `devenv shell luxnix inspect <host>` ([quickstart](boot-storage-quickstart.md)) |
| Plaintext machine whose contents must survive | [Preserve an existing installation](boot-storage-quickstart.md#preserve-an-existing-installation) |
| Emergency mode, or a rebuild is refused | [Boot storage recovery](boot-storage-recovery.md) |
| Encryption was interrupted | [Resume interrupted encryption](boot-storage-recovery.md#resume-interrupted-encryption) |
| Host still uses the container layout | [Unmigrated hosts](legacy-storage-recovery.md) |
| Running the conversion from RAM | [RAM migration environment](migration-environment.md) |
| Signing generations for Secure Boot | [Fleet Secure Boot](secure-boot.md) |

## Configuration and disk agree

Each host's configuration states its root layout; the disk has its own state. They
must match:

| Disk state | Matching layout | Root device |
| --- | --- | --- |
| `plaintext` | `legacy-containers` | The partition itself |
| `encrypting` | None; resume the conversion first | |
| `encrypted` | `boot-luks` (module default) | `/dev/mapper/cryptroot` |
| `unknown` | None; stop and inspect | |

- Set `layout` per host in `ansible/inventory/host_vars/<host>.yml`.
- Only the host itself can read its disk: `luxnix-root-preflight` checks it at every
  activation, and `luxnix-boot-recover classify` reads it from recovery media.
- A saved migration stage records history; the disk is the proof.
- Each generation boots only the disk state it was built for. Keep a matching
  generation and recovery media at hand.

## Three workflows

```text
                     devenv shell luxnix   (guidance; changes nothing)
                              │
        ┌─────────────────────┼──────────────────────┐
        ▼                     ▼                      ▼
 install --profile      inspect <host>             migrate
 FRESH: erases disk     EXISTING: read-only        PRESERVE: in place
 bundle on installer    then normal deployment     RAM migration environment
        │                                            │
        └──────────── cold boot, unlock, accept ◄─────┘
```

## Preservation lifecycle

`devenv shell luxnix migrate` moves a host through these stages, recorded in
`lifecycle.json` in `/recovery/luxnix-state/<host>`. Repeating a stage is a no-op;
stages always run in order. A failed stage resumes where it stopped.

```text
 preparing ──► migrating ──► verifying ──► activating ──► completed
```

| Stage | What happens | Where | Disk changes |
| --- | --- | --- | --- |
| preparing | Plan pinned to revision, closure and disk identity; source copied to the recovery drive; encrypted host backup updated and verified; custody checked | Installed host | None |
| migrating | Boot default held on the migration entry; root encrypted in place; container data copied in | RAM migration environment | Yes, after typed `ENCRYPT IN PLACE` |
| verifying | Disk read against the plan: header, UUID, mapping, subvolumes, tested credential | Same session | None |
| activating | Matching `boot-luks` system installed; boot default handed to it and verified | Same session | Boot entries only |
| completed | Cold boot of the planned system, then acceptance recorded | Installed host | None |

Then set the host to `boot-luks`, pin the LUKS UUID reported by `verify`,
regenerate, and preview `devenv shell luxnix retire-containers`.

## The boot default during conversion

The boot default always matches the disk:

```text
 disk:     plaintext ──────► encrypting ──► encrypted ──────────► encrypted
 default:  old generation ─► migration entry ────────────────────► new generation
                           ▲ just before the                     ▲ by install,
                           │ first disk write                    │ then verified
 a reboot: old system        migration environment                new system
```

- If the conversion stops before the disk changes, the old default returns.
- Approvals that started the conversion stay valid until it is installed.
- The planned system may come from the host's own store, mounted at `/mnt`.
- Started from another boot entry, the environment warns instead: stay in the
  session until installation reports the new default.
- The `boot-default-hold` VM test checks this on real UEFI firmware, including
  power cuts.

## Operator commands

Run these as your normal user from a reviewed checkout, unless noted.

| Command | Effect | Repeatable |
| --- | --- | --- |
| `devenv shell luxnix prepare` | Writes the plan to the recovery drive | Yes |
| `devenv shell luxnix status` | Reads saved state | Yes |
| `devenv shell luxnix migrate` | Guides each step; asks before every disk change | Yes, resumes |
| `devenv shell luxnix verify` | Reads the disk against the plan | Yes |
| `devenv shell luxnix recover --partition <path>` | Prints the procedure for that disk state | Yes |
| `devenv shell luxnix recover --assessor <name> --apply` | Accepts a reviewed layout after confirmation | Yes, rechecks first |
| `devenv shell luxnix retire-containers --apply` | Deletes retired containers after typed approval | Once |
| `devenv shell migration-boot kexec --apply` (target host) | Builds and starts the RAM environment without a reboot; pins its SSH key | Yes; asks to confirm |
| `luxnix-migration run --apply` (RAM environment, root) | Runs the plan's own source; asks before every disk change | Yes, resumes |
| `luxnix-root-preflight status` (host) | Compares the running configuration with the disk | Yes |
| `luxnix-boot-recover classify` (recovery ISO) | Reports the disk state | Yes |
| `luxnix-boot-recover restore --apply` (recovery ISO) | Selects a matching generation | Yes |

### State file permissions

Migration state belongs to the operator who created it, private to that user.
Commands tighten read-only exposure automatically, for example `0644` to `0600`,
and report it. They stop and name the path for anything that needs a decision:
write access for others, another owner, a writable parent directory, or media
without permissions such as FAT. In the RAM environment, root works with the
operator's state and hands new files back to that operator afterwards.

## Every activation is checked

Each generation carries its storage contract in `/etc/luxnix/root-storage.json`.
Before activation, the host compares it with the real disk:

```text
 nixos-rebuild · nho/nhb · Ansible · luxnix-safe-activate · nixos-install
                                │
                                ▼
       luxnix-root-preflight check   (also when NIXOS_NO_CHECK=1)
       partition, LUKS2 header, mapping, mounts, subvolumes, ESP, credentials
                    │                              │
                 matches                        mismatch
          activation continues        refused, and removed from the boot menu
```

Physical mismatches always stop. Other findings accept one audited 15-minute
[override](boot-storage-recovery.md#audited-override) for one exact system.

## Recovery

Build the recovery ISO (`nix build .#luxnix-recovery-iso`) before migrating. It
holds only storage tools, so it works whatever the state of application builds.

```text
 luxnix-boot-recover classify --partition <root>
        │
 plaintext ──► mount, restore a plaintext generation
 encrypting ─► boot the migration entry, luxnix-migration run --apply
 encrypted ──► unlock, mount, restore a boot-luks generation
 unknown ────► stop, compare with the plan, image the disk
```

## Where things live

| What | Location |
| --- | --- |
| Host layout and disk facts | `ansible/inventory/host_vars/<host>.yml` |
| Fleet volumes and bind mounts | `ansible/inventory/group_vars/operator_unlocked_secrets.yml` |
| Generated host configuration | `systems/x86_64-linux/<host>/default.nix` (regenerate with Autoconf) |
| Storage module, initrd unlock, activation guard | `modules/nixos/luxnix/operator-unlocked-storage/` |
| Disk layout for `boot-luks` hosts | `systems/x86_64-linux/encrypted-layout.nix` |
| Migration, preflight, recovery code | `lx_administration/storage/` |
| RAM launcher | `lx_administration/storage/installer_handoff.py` (`luxnix-migration`) |
| Recovery ISO | `lx_administration/storage/recovery-image.nix` |
| Migration state and journals | `/recovery/luxnix-state/<host>/` |
| Plan source for the RAM environment | `/recovery/luxnix-state/sources/<revision>/` |
| Encrypted host backup | `/recovery/luxnix-backup-<host>.luks`, key in custody (`<custody>/host-backup-<host>.key`) |
| LUKS header backup | `/recovery/luxnix-state/<host>/header-after-conversion-*/luks.header` |
| Storage contract per generation | `/etc/luxnix/root-storage.json` |
| Override and audit records | `/run/luxnix/root-guard-override.json`, `/var/lib/luxnix/root-guard-audit.jsonl` |

Mapping names are listed in the
[shared encryption contract](boot-storage-migration.md#shared-encryption-contract).

## Host-specific settings

Set these in the host's inventory only:

| Option | Purpose |
| --- | --- |
| `layout` | `legacy-containers` while plaintext; `boot-luks` after acceptance |
| `rootIdentity.disk` | Persistent disk path, overriding the Disko-derived one |
| `rootIdentity.requirePersistentDisk` | Require a `/dev/disk/by-id` disk path |
| `rootIdentity.luksUUID` | Pin the root LUKS2 UUID after conversion |
| `plaintextRootBridge` | Disposable test machines only |

A cold boot on the machine itself is the final proof; tests and VMs prepare for it.
