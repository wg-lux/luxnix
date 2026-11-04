# LuxNix storage: one operator workflow

Run controller commands from the reviewed LuxNix checkout in a private terminal
(no screen sharing, session recording or terminal logging). Keep console access
and trusted recovery media ready. Replace `<host>` and `<state>` with the approved
inventory host and existing migration state directory; do not paste placeholders.

## Shared layout

| Purpose | Standard mapper / paths |
| --- | --- |
| Encrypted root | `/dev/mapper/cryptroot` |
| Separate application storage | `/dev/mapper/luxnix-app-storage` |
| Separate secrets storage | `/dev/mapper/luxnix-secrets` |
| Secrets consumed by applications | `/etc/secrets`, `/etc/secrets/vault` |

New installations use the shared LUKS2 Disko layout with host-owned disk sizes.
If RAID exists, encryption is above RAID. Secrets normally live directly on the
encrypted root; a dedicated secrets filesystem uses `luxnix-secrets`.
Retained containers, such as gc-10's, keep their files, UUIDs and data. Their
standard bind paths are supplied by shared inventory. A rebuild never formats
an existing disk, converts plaintext root, or moves secrets automatically.

## New installation or root migration

First prepare the reviewed hardware plan and recovery evidence using the
[installation guide](boot-storage-migration.md#guided-operator-workflow).
A migration requires retained disks or a verified backup and restore test.
Use the same saved state after an interruption; do not restart disk formatting.

On the controller:

```sh
devenv shell check-connectivity <host>
devenv shell boot-storage-migration status --state <state>
```

As root in the trusted installer, with the reviewed package and state available:

```sh
python -m lx_administration.storage.boot_migration check --state <state> --stage provision
```

Only after that passes, provision the approved disks with their reviewed Disko
layout and mount the target at `/mnt`. Choose and record the prompted LUKS
password in your password manager. Stage the administrator credential using
[the account guide](admin-passwords.md#6-install-on-a-new-machine); it is separate
from the disk password. Restore existing application keys, salts and data onto
protected storage when migrating. Then run:

```sh
python -m lx_administration.storage.boot_migration prepare-access --state <state>
```

Record the `prepared` evidence from the guide, then:

```sh
python -m lx_administration.storage.boot_migration check --state <state> --stage install
python -m lx_administration.storage.boot_migration install --state <state>
```

Confirm the displayed host and disks. Arrange the first boot with console
recovery available; verify disk unlock, administrator login and application data.

## Save and verify disk-password custody

After the installed host is reachable, use the controller's existing encrypted
vault and configured independent recovery envelopes. The custody selection must
already exist (`storage-recovery-custody prepare` in the installation guide).

```sh
devenv shell storage-provision setup --host <host> --volume cryptroot --apply
```

Add `--sudo-password-file <private-file>` if passwordless sudo is unavailable.
For retained containers replace `cryptroot` with `luxnix-secrets`, then repeat
for `luxnix-app-storage`. Omit `--apply` to preview. Setup tests a stored key or
asks privately for the current password, verifies both encrypted recovery copies,
then shows it once and asks for `SAVED`. Acknowledged keys are not shown again.
Wrong passwords or mismatched identities stop setup; no keys are removed.

## Rebuilds and retained containers

On an installed boot-LUKS host, `sudo luxnix-setup-boot-password` prepares the
first activation; `--change` explicitly adds a new password while keeping recovery
slots. It stores a verification receipt only. Controller custody above preserves
the verified recovery password; it does not rotate or replace an existing record.
Ordinary rebuilds with an unchanged LUKS header do not prompt again.

For retained containers, use `sudo luxnix-operator-storage start` to unlock and
start consumers. For stale mount overrides, preview `sudo luxnix-normalize-storage`,
stop its listed writers, then run `sudo luxnix-normalize-storage --apply` and
restart consumers. See [the recovery guide](legacy-storage-recovery.md).
Never bypass encrypted mount checks or erase a volume to fix a password failure.
Keep recovery copies until cold boot, fresh login and old-data decryption pass.
