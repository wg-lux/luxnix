# LuxNix installation: operator checklist

Use this checklist for one approved machine. Success means it boots, an
administrator can log in, and restored applications can read their existing data.
Keep recovery copies until those checks are recorded.

If you use the application but do not administer the machine, ask the named
operator for the maintenance window and confirmation before resuming work.
If you are a first-time operator, have an experienced administrator prepare and
review the disk plan with you before step 1. If work already started, use
[resume instructions](changelog.md#continue-an-installation-or-migration) first.

### Know where to run each command

| Term | Meaning |
| --- | --- |
| Controller | The administrator's computer containing the reviewed LuxNix checkout. |
| Target | The machine being installed; confirm its name and disk serials against the plan. |
| Trusted installer | Recovery media booted on the target, separate from its installed OS. `root` means its administrator account. |
| State directory | The saved plan and progress evidence. Keep this on independent encrypted storage and reuse it after interruptions. |
| Root encryption | Protection for the operating-system disk. Application-file encryption is a separate layer. |

Run controller commands from its reviewed LuxNix checkout. Replace `<host>` with
the inventory name, `<spec>` with
your [private disk-selection YAML](boot-storage-migration.md#guided-operator-workflow),
and `<state>` with an absolute path on independent encrypted storage.
Angle brackets mark values to replace; do not paste them literally. Obtain these
values from the approved plan rather than guessing from a disk's size or order.

## 1. Select storage and prepare recovery

Use `boot-luks` and `root_encryption: luks2`. Plain-root installation is retired.
Regenerate and review the host before planning; retain existing recovery keys.

For **new empty disks**, set `installation: fresh` and `source_retention: new-disks`.
Test the installer and independent administrator access; record `recovery`.
For **migration**, retain old disks or a verified whole-disk image, authenticate
backups and test a restore. Record `recovery`, `backup`, `restore`, including a
fresh [source admission report](boot-storage-migration.md#readiness-observations-versus-admission).
Use the [evidence procedure](boot-storage-migration.md#guided-operator-workflow)
and the exact check names printed by `status`.

Confirm the machine, address, disk serials, release revision and `flake.lock`:

```sh
devenv shell check-connectivity <host>
devenv shell boot-storage-migration plan --spec <spec> --state <state>
devenv shell boot-storage-migration status --state <state>
```

Configure [early SSH unlock](boot-storage-migration.md#remote-ssh-root-unlock)
only for encrypted root. Do not combine it with the current controller-held
Secure Boot signer. Keep required Secure Boot policy and use console recovery.

## 2. Prepare and install from trusted recovery media

Run these commands **as root in the trusted installer**, with the reviewed Python
package available. Preserve the checkout, state and evidence at their planned
absolute paths; make the built system available locally.

```sh
python -m lx_administration.storage.boot_migration check --state <state> --stage provision
```

After that check passes, provision only the approved disks using the reviewed
layout; mount the target at `/mnt`. Stage valid administrator credentials using
the [account guide](admin-passwords.md#6-install-on-a-new-machine).
For a migration, [restore existing data and keys](boot-storage-migration.md#reprovision-and-restore-explicit-destructive-operator-action)
into protected storage. Never restore protected application data onto plain root.
Then run:

```sh
python -m lx_administration.storage.boot_migration prepare-access --state <state>
```

For SSH unlock, pin the printed public host key on the operator computer through
this trusted installer session. Record the `prepared` assessment, then run:

```sh
python -m lx_administration.storage.boot_migration check --state <state> --stage install
python -m lx_administration.storage.boot_migration install --state <state>
```

Read the displayed machine and disks. Confirm only the approved plan. Wait for
success before arranging the first reboot with the recovery operator present.

## 3. Boot and accept

For encrypted root with SSH unlock, use the configured management address,
dedicated private SSH key and pinned host key:

```sh
ssh -tt -p 2222 -i <operator-key> -o StrictHostKeyChecking=yes root@<unlock-address>
```

Enter the disk credential. After boot, reconnect using normal administrator
SSH. If you mistype the disk credential, reconnect and wait for the next prompt.
For console unlock, enter the same disk credential at the local prompt.

Verify administrator login and cold-boot recovery. For restored applications,
verify data mounts, database queries and old-data decryption. Complete the applicable
[cold-boot and recovery checks](boot-storage-migration.md#acceptance-recovery-and-rollback-limits),
then record `acceptance`. Keep old disks and recovery copies until retention
removal is separately approved.

## If a step fails

- Keep the machine in its current state. Give the operator the failed step,
  time, non-secret error and plan identifier through the approved support channel.
  Do not include passwords, private keys, patient data or full environment dumps.
- Run `status --state <state>` with the same migration command. Keep its state,
  evidence and recovery copies; resolve the reported check before continuing.
- After a snapshot interruption, let automatic cleanup finish; inspect snapshot
  `status` and use [journal recovery](boot-storage-migration.md#snapshot-backups-from-the-existing-gc-09-and-gc-10-installations)
  if writers remain stopped.
- After an interrupted installation, review the target and record
  `install-recovery` evidence before using `install --retry-interrupted`.
- After lost SSH during activation, reconnect and inspect the retained operation
  before retrying; follow [activation recovery](secure-boot.md#how-a-deployment-is-signed).
- Never replace a missing existing volume key or rerun disk formatting to recover.
  Use the retained disks or verified restore. A generation rollback cannot undo a
  format or database migration.
