# Client and server encryption: one operator workflow

This is the canonical short guide for both client and server installations
(reviewed 2026-11-05). The shared target is **`boot-luks` with LUKS2 root**;
`legacy-containers` is retained recovery compatibility, not a second installation
design. Repository settings describe intent, not the disks currently installed.

Run controller commands from the reviewed LuxNix checkout in a private terminal
(no screen sharing, session recording or terminal logging). Keep console access
and trusted recovery media ready. Replace `<host>` and `<state>` with the approved
inventory host and existing migration state directory; do not paste placeholders.

## Shared encryption contract

| Purpose | Standard mapper / paths |
| --- | --- |
| Encrypted root | `/dev/mapper/cryptroot` |
| Separate application storage | `/dev/mapper/luxnix-app-storage` |
| Separate secrets storage | `/dev/mapper/luxnix-secrets` |
| Secrets consumed by applications | `/etc/secrets`, `/etc/secrets/vault` |

New installations use the shared LUKS2 Disko layout with host-owned disk sizes.
EFI remains unencrypted. Root protects `/nix`, homes, persistent logs, service
secrets and secondary-volume keyfiles. Separate data volumes unlock in stage 2
using private keys on encrypted root, never keys embedded in EFI or the Nix store.
MD arrays are encrypted above RAID; retained multi-device Btrfs layouts require
every member to be encrypted. Active disk swap must also be protected or disabled.
Secrets normally live on encrypted root; a dedicated secrets filesystem uses
`luxnix-secrets`.
Retained containers, such as gc-10's, keep their files, UUIDs and data. Their
standard bind paths are supplied by shared inventory. A rebuild never formats
an existing disk, converts plaintext root, or moves secrets automatically.

| Client / desktop | Server / headless |
| --- | --- |
| Unlock root locally through Plymouth, then authenticate to the selected Linux account. | Unlock root from a console, or use explicitly configured restricted initrd SSH. |
| SDDM shows the account chooser fleet-wide; `roles.desktop.addons.plasma.bootAutoLogin = false` is enforced. | Initrd SSH is opt-in, key-authenticated and limited to the disk-unlock prompt; it is not a maintenance shell or unattended unlock. |
| Linux, LUKS and KWallet passwords are independent. Rebuilds refuse account-password drift; rotation requires explicit confirmation or password entry. | Ordinary SSH and services become available after boot and their dependencies; verify independent admin SSH recovery. |

Root unlock does not require Vault, OpenBao or network connectivity. Application
startup may still require authenticated secret delivery. Missing storage, keys or
required secrets must block consumers; no plaintext fallback is permitted.
Application-level encryption, original master keys/salts, and backup encryption
remain separate requirements. Secure Boot authenticates the boot chain separately;
LUKS alone does not establish it or filesystem integrity. See the
[technical reference](boot-storage-migration.md#architecture-and-scope) and
[signing guide](secure-boot.md).

## New installation or root migration

First prepare the reviewed hardware plan and recovery evidence using the
[installation guide](boot-storage-migration.md#guided-operator-workflow).
A migration requires retained disks or a verified backup and restore test.
Use the same saved state after an interruption; do not restart disk formatting.
Disposable data permits a separately authorized fresh provisioning plan, not
implicit permission to erase disks. Confirm hardware identities and preserve or
explicitly re-enroll machine/application credentials before provisioning.

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

First verify the actual root and data mappings against the target configuration.
If root is still plaintext, follow the installation/migration procedure above;
neither `nixos-rebuild boot` nor the subsequent reboot encrypts it in place.
Use the selected host's build, not another host's closure. Check the running,
booted and system-profile closures and bootloader default independently: they can
disagree after an interrupted installation. Retain a known-bootable generation.

If activation reports a missing `/dev/mapper/cryptroot`, run the candidate's
`sudo ./result/sw/bin/luxnix-setup-root-encryption` (replace `./result` with your
actual build result). It reports the configured host/device and mounted root,
checks all root filesystem members, and explains the required next step.
It never formats disks, opens mappings, changes keyslots or activates a generation.
An already encrypted but mismatched root needs configuration/recovery review;
a plaintext root needs the installation/migration workflow above. Creating an
unrelated mapper named `cryptroot` does not fix the mounted root.

Once root matches the candidate, explicitly run
`sudo ./result/sw/bin/luxnix-setup-root-encryption --setup-password` to verify the
existing disk password through the canonical helper. Then run
`sudo ./result/sw/bin/luxnix-verify-boot-storage` and retry the rebuild only after
all checks pass. A successful root-only check does not verify secondary volumes,
application recovery, or physical next-boot acceptance.

On an installed boot-LUKS host, build the target generation first and run its
`luxnix-setup-boot-password` helper with sudo to prepare the first activation
(use the actual build-result path). `--change` explicitly adds a new password while keeping recovery
slots. It stores a verification receipt only. Controller custody above preserves
the verified recovery password; it does not rotate or replace an existing record.
Ordinary rebuilds with an unchanged LUKS header do not prompt again.

For retained containers, use `sudo luxnix-operator-storage start` to unlock and
start consumers. For stale mount overrides, preview `sudo luxnix-normalize-storage`,
stop its listed writers, then run `sudo luxnix-normalize-storage --apply` and
restart consumers. See [the recovery guide](legacy-storage-recovery.md).
Never bypass encrypted mount checks or erase a volume to fix a password failure.
Keep recovery copies until cold boot, fresh login and old-data decryption pass.
Accept each host separately: offline root unlock, chooser/login and sudo/SSH,
expected encrypted mounts, secret delivery, application startup, existing-data
decryption and independent recovery. A build or VM pass is not physical acceptance.
