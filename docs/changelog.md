# Operator change notes

## 2026-11-13 — RAM conversion: earlier checks, fewer commands

- `luxnix-migration run` mounts the plan's recovery drive itself and runs the
  read-only `btrfs check` before the typed approval and the passphrases. A
  failed check keeps its full report in
  `/run/luxnix-migration/btrfs-check-<partition>.log` (in RAM) and changes
  nothing.
- `migration-boot kexec` refuses a `controller_cidr` that excludes the wired SSH
  session it is run from, and marks an address it cannot verify.
- The conversion code runs from the plan's saved source: update the checkout on
  the target and rerun `devenv shell luxnix migrate` so the plan uses this
  revision, then start the RAM environment again. A plan whose earlier run
  stopped before any partition was encrypted is replaced automatically; it no
  longer stops with "The checkout or flake.lock changed after this plan
  started".
- A `migration-boot kexec` start checks its store image in memory and restarts
  into the installed system after 15 seconds when it is damaged or the RAM
  kernel crashes, instead of hanging.

## 2026-11-04 — NetworkManager startup

The shared boot module explicitly starts `NetworkManager` and
`NetworkManager-dispatcher` from `multi-user.target` when NetworkManager is enabled,
following [nixpkgs PR #368791](https://github.com/NixOS/nixpkgs/pull/368791).
The pinned nixpkgs already has these targets; this makes the local boot policy
explicit and does not establish the cause of gc-09's network outage.

## Unreleased — 2026-11-02

Use these instructions with the reviewed checkout for your machine. Start new
work with the [boot-storage operator checklist](boot-storage-quickstart.md).
These changes do not migrate a running machine or establish physical acceptance.
For help choosing a guide, use the [task-based documentation home](index.md).

### What changed

- Installation now checks the selected machine, disks, recovery evidence, mounts
  and administrator access before installing the reviewed system.
- Snapshot recovery and activation watchdogs retain operation state for recovery;
  retries do not authorize formatting, replacement keys or an automatic reboot.
- Encrypted-root recovery supports explicitly configured operator SSH unlock.
  Recovery custody must remain usable independently of the machine being restored.
- The single-path decision supersedes plain-root installation. New installations
  require boot LUKS2; existing gc-09/gc-10 recovery remains until physical acceptance.
- Shared encryption checks now reject missing or plaintext Btrfs members.
  Credential creation and every export reject incomplete or mismatched pairs.
- Hub backups pause writers across a fresh database/media capture and restore
  their prior state after failures. Plan for backup downtime before deployment.
- LX-Annotate 1.7.2 installs from a complete hashed offline wheelhouse, including
  pinned builds for source-only dependencies. Hub node provisioning delegates to
  its tested installed command; recovery/authentication parity remains gated.
- LXENC v2 adds authenticated file endings and safe range reads. Application
  rotation now upgrades v1 with the existing active key and supports repeatable
  resume. Follow the [EndoReg v1 and mid-migration instructions](https://github.com/wg-lux/endoreg-db/blob/main/docs/secret_rotation.md#v1-machines-and-interrupted-media-migrations)
  before enabling v2 writes; this does not require disk reprovisioning.

### Existing installations

- Keep an unmigrated machine on its explicit `legacy-containers` selection.
  Preserve its volume identities, enrolled keys and recovery copies. Follow
  [legacy maintenance](boot-storage-migration.md#temporary-compatibility-and-removal)
  before changing its layout; activating `boot-luks` does not convert disks.
- Test a backup restore and retain old disks or a verified whole-disk image
  before approving reprovisioning. Keep application keys and salts with the
  protected recovery material. Verify old media decryption after restore.
- Treat LXENC v1/v2 as application-file formats managed by EndoReg/LX-Annotate.
  Boot LUKS protects disks independently. Do not rotate application keys or
  rewrite LXENC files merely to adopt this boot workflow; follow the separate
  [secret rotation procedure](secret-rotation.md) when rotation is intended.

### Continue an installation or migration

1. Keep the same private state directory, evidence, checkout and planned paths.
   On the controller, replace `<state>` below with that absolute directory:

   ```sh
   devenv shell boot-storage-migration status --state <state>
   ```

2. Complete the next reported assessment or check. Reuse existing credentials;
   `prepare-access` preserves valid existing access material. Do not delete
   state, replace a missing enrolled key or repeat formatting to clear a failure.
3. For an interrupted install, inspect the target and record `install-recovery`
   evidence. Only then use `install --retry-interrupted` from trusted installer
   media, following the [guided workflow](boot-storage-migration.md#guided-operator-workflow).
   A successful install is not repeated; an approved retry installs the same
   closure without a disk-format phase.
4. After a snapshot interruption, inspect snapshot `status`; use the
   [snapshot journal recovery procedure](boot-storage-migration.md#snapshot-backups-from-the-existing-gc-09-and-gc-10-installations)
   if automatic cleanup leaves writers stopped. After lost SSH during activation,
   reconnect and inspect the retained operation before retrying through the
   [activation recovery procedure](secure-boot.md#how-a-deployment-is-signed).
   Confirm stateful compatibility before rollback; a system generation cannot
   undo formatting or database migrations.
5. Verify normal administrator access, a cold boot and restored applications.
   Record acceptance before separately approving removal of recovery copies.

### New installations

Use `boot-luks` and `root_encryption: luks2`. The earlier plain-root policy is
superseded. Fresh encrypted installations on verified empty disks retain their
recovery and preparation gates without requiring a nonexistent source backup.

### Choose recovery access before installation

For encrypted root, explicitly configure
[operator SSH unlock](boot-storage-migration.md#remote-ssh-root-unlock), including
the management interface, allowed sources and dedicated operator key. Pin the
printed SSH host key through the trusted installer session and keep console
recovery available. Reconnect after a mistyped disk credential.

Do not combine early SSH unlock with the current controller-held Secure Boot
signer. Preserve required Secure Boot policy and use console unlock until a
compatible signing path is supported. Keep firmware enrollment and reboot as
separate approved steps; follow the [Secure Boot procedure](secure-boot.md).
