# Encrypted storage map

This page is an overview of encrypted root storage. It names the parts, shows how
they connect and says which page to open. The [current contract](https://github.com/wg-lux/luxnix/blob/main/boot-storage.yml)
holds the requirements.

## Which page do I need?

| Situation | Start here |
| --- | --- |
| New machine, or one whose contents may be erased | [Fresh installation](boot-storage-quickstart.md#fresh-installation) |
| Machine already encrypted; check it | `devenv shell luxnix inspect <host>`, see [quickstart](boot-storage-quickstart.md) |
| Plaintext machine whose contents must survive | [Preserve an existing installation](boot-storage-quickstart.md#preserve-an-existing-installation), then the [migration reference](boot-storage-migration.md) |
| Host stops in emergency mode, or a rebuild is refused | [Boot storage recovery](boot-storage-recovery.md) |
| Encryption was interrupted | [Resume interrupted encryption](boot-storage-recovery.md#resume-interrupted-encryption) |
| Host still runs the old container layout | [Unmigrated hosts](legacy-storage-recovery.md) |
| Booting a separate RAM environment for the conversion | [RAM migration](migration-environment.md) |
| Signing generations for Secure Boot | [Fleet Secure Boot](secure-boot.md) |

## Two facts that must agree

Every problem in this area comes from a mismatch between two things:

```text
  What the configuration expects                What is on the disk
  (inventory -> generated Nix)                  (only the host can see it)

  storage.operatorUnlocked.layout               root partition signature
  ┌───────────────────────┐                     ┌──────────────────────────┐
  │ luks-containers       │  must match  ─────► │ plaintext Btrfs          │
  │ boot-luks (default)   │  must match  ─────► │ LUKS2, cryptroot open    │
  └───────────────────────┘                     └──────────────────────────┘
                                                  plus: encrypting (stopped
                                                  part-way) and unknown
```

- `layout` is set per host in `ansible/inventory/host_vars/<host>.yml`; the shared
  module default is `boot-luks`.
- Evaluation is pure and cannot see the disk. Only the target host can, through
  `luxnix-root-preflight` at activation and `luxnix-boot-recover classify` from
  recovery media.
- A saved migration stage is a record of history, never proof of disk state.

| Disk state | Generations that can boot it |
| --- | --- |
| `plaintext` | Only `legacy-containers` ones (root mounted directly) |
| `encrypting` | None until encryption is resumed and finished |
| `encrypted` | Only `boot-luks` ones (root on `/dev/mapper/cryptroot`) |
| `unknown` | None; stop and inspect |

A plaintext generation does not boot an encrypted disk, and an encrypted one does
not boot a plaintext disk. Old boot entries of the other kind are not a fallback.

## The three workflows

```text
                       devenv shell luxnix   (guidance only, changes nothing)
                                │
          ┌─────────────────────┼──────────────────────────┐
          ▼                     ▼                          ▼
   install --profile      inspect <host>                 migrate
   FRESH (erases disk)    EXISTING (read-only)           PRESERVE (in place)
          │                     │                          │
   fresh_install.py       verify mounts, keys,       boot_setup.py
   luxnix-install         admin hash                 boot_migration.py
   bundle on live         then normal deployment     (see lifecycle below)
   installer media
          │                                                │
          └──────────── cold boot, unlock, accept ◄────────┘
```

## Preservation lifecycle

`devenv shell luxnix migrate` moves one host through these stages. The record is
`lifecycle.json` in the host's state directory on the recovery drive
(`/recovery/luxnix-state/<host>`). Repeating a stage changes nothing; skipping one
is refused.

```text
 preparing ──► migrating ──► verifying ──► activating ──► completed
     │             │             │              │
     └─────────────┴──────┬──────┴──────────────┘
                          ▼
                       failed ── resumes only at the stage it left
```

| Stage | What happens | Where it runs | Disk changes |
| --- | --- | --- | --- |
| preparing | Plan pinned to revision, closure and disk identity; backup and credential custody checked | Running host | None |
| migrating | `cryptsetup reencrypt --encrypt` of the Btrfs root; container data copied in | Trusted installer media | Yes, after typed `ENCRYPT IN PLACE` |
| verifying | Disk read against the plan: LUKS2 header, UUID, mapping, subvolumes, tested credential | Installer or host | None |
| activating | Matching `boot-luks` system installed | Installer media | Boot entries only |
| completed | Real cold boot of the planned closure, then acceptance recorded | Host after reboot | None |

After `completed`: set the host to `boot-luks` in its inventory, pin the LUKS UUID
reported by `verify`, regenerate, and only then preview
`devenv shell luxnix retire-containers`.

## Operator commands

All run from a reviewed checkout as the normal user unless noted.

| Command | Changes | Safe to repeat |
| --- | --- | --- |
| `devenv shell luxnix prepare` | Writes the plan to recovery media only | Yes |
| `devenv shell luxnix status` | Reads saved state; may tighten state file permissions | Yes |
| `devenv shell luxnix migrate` | Asks before each disk change | Yes, it resumes |
| `devenv shell luxnix verify` | Reads the disk against the plan; may tighten state file permissions | Yes |

| `devenv shell luxnix recover --partition <path>` | Nothing; prints the procedure for that disk state | Yes |
| `devenv shell luxnix recover --assessor <name> --apply` | Accepts an already reviewed layout; never formats | Rechecks and asks for confirmation each time |
| `devenv shell luxnix retire-containers --apply` | Deletes retired container files after typed approval | No |
| `luxnix-root-preflight status` (on the host) | Nothing | Yes |
| `luxnix-boot-recover classify` (recovery ISO) | Nothing | Yes |
| `luxnix-boot-recover restore --apply` (recovery ISO) | System profile and boot entries only | Yes |

### State file permissions

Migration state must belong to the operator running the command, with no access
for group or others. Every command checks each state path it reads. A path that
others can only read, such as `0644` or `0755`, is tightened automatically and
reported as `Restricted <path> from <old> to <new>`. These are refused, naming
the path and the fix, because they need a human decision:

- Write access for group or others: another user may have changed the content.
- A different owner, usually from running a step with `sudo`.
- A parent directory writable by group or others.
- Recovery media that cannot store permissions, such as FAT or exFAT.

## What guards every activation

Each generation carries its storage expectation in `/etc/luxnix/root-storage.json`.
Before it is activated, the target host compares that with the real disk.

```text
 nixos-rebuild switch|boot|test   nho / nhb   Ansible   luxnix-safe-activate   nixos-install
                                      │
                                      ▼
              system.preSwitchChecks.rootStorage  (also runs when NIXOS_NO_CHECK=1)
                                      │
                                      ▼
            luxnix-root-preflight check  ── reads the real disk, partition,
                                      │     LUKS2 header, mapping, mounts,
                                      │     subvolumes, ESP space, credentials
                    ┌─────────────────┴──────────────────┐
                    ▼                                    ▼
                 matches                             mismatch
           activation continues      refused; the generation is removed from the
                                      system profile so it cannot take a boot slot
```

Physical mismatches cannot be overridden. Other findings allow one audited,
15-minute override for one exact closure; see
[audited override](boot-storage-recovery.md#audited-override). Overrides and
`NIXOS_NO_CHECK` use are logged to `/var/lib/luxnix/root-guard-audit.jsonl`.

## Recovery paths

```text
 Host will not boot ──► boot the recovery ISO (nix build .#luxnix-recovery-iso)
                           │
                           ▼
                luxnix-boot-recover classify --partition <root>
                           │
     ┌──────────────┬──────┴───────┬────────────────┐
     ▼              ▼              ▼                ▼
 plaintext      encrypting      encrypted        unknown
 mount, then    rerun           unlock, mount,   stop; compare
 restore a      `luxnix         restore a        with the plan;
 plaintext      migrate`        boot-luks        take a disk image
 generation     (resumes)       generation
```

Build the ISO before starting a migration. It contains only storage tools, so a
broken application build cannot block recovery.

## Where things live

| What | Location |
| --- | --- |
| Host layout and disk facts | `ansible/inventory/host_vars/<host>.yml` (`storage.operatorUnlocked.*`) |
| Fleet volumes and bind mounts | `ansible/inventory/group_vars/operator_unlocked_secrets.yml` |
| Generated host configuration | `systems/x86_64-linux/<host>/default.nix` (regenerate with Autoconf; do not edit) |
| Layout, volumes, unlock services | `modules/nixos/luxnix/operator-unlocked-storage/default.nix` |
| Initrd unlock and root mounts | `modules/nixos/luxnix/operator-unlocked-storage/boot.nix` |
| Activation guard and its options | `modules/nixos/luxnix/operator-unlocked-storage/root-guard.nix` |
| Disk layout for `boot-luks` hosts | `systems/x86_64-linux/encrypted-layout.nix` |
| Preflight, lifecycle, recovery logic | `lx_administration/storage/root_guard.py`, `migration_lifecycle.py`, `root_recovery.py` |
| Migration and fresh install logic | `lx_administration/storage/boot_setup.py`, `boot_migration.py`, `fresh_install.py` |
| Recovery ISO | `lx_administration/storage/recovery-image.nix` |
| Migration state and journals | `/recovery/luxnix-state/<host>/` (`lifecycle.json`, `progress.json`, `provision.json`) |
| Per-generation storage contract | `/etc/luxnix/root-storage.json` on the host |
| Override and audit records | `/run/luxnix/root-guard-override.json`, `/var/lib/luxnix/root-guard-audit.jsonl` |

Device mapping names are listed in the
[shared encryption contract](boot-storage-migration.md#shared-encryption-contract).

## Host-specific settings

These options are host facts, set in a host's inventory only, never fleet-wide:

| Option | Purpose |
| --- | --- |
| `layout` | `legacy-containers` while the root is plaintext; `boot-luks` after acceptance |
| `rootIdentity.disk` | Persistent disk path that overrides the one derived from the Disko layout |
| `rootIdentity.requirePersistentDisk` | Refuse activation if the disk is named like `/dev/nvme0n1` |
| `rootIdentity.luksUUID` | Pin the root LUKS2 UUID after conversion |
| `plaintextRootBridge` | Disposable test machines only; never on a real host |

Repository tests and VM checks do not prove that a real host boots. Physical
acceptance always needs a cold boot on the machine itself.
