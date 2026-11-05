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

Use `boot-storage-setup` for the sequential workflow; `boot-storage-migration`
remains the evidence and install-only interface. Neither command encrypts a
running plaintext root in place. Work on **one host at a time**, accepting its
cold boot and recovery before proceeding to the next host.

1. **Review a clean, durable release.** On the target, collect a specification
   without changing storage. Use its reviewed checkout and actual inventory name:

   ```sh
   devenv shell boot-storage-setup observe --checkout <checkout> --host <host> --installation disposable --source-retention discard-approved
   ```

   Save the YAML privately on encrypted controller storage. Observation requires
   permission to read the hardware UUID. It reads only the configured disk IDs;
   it never substitutes another disk. Review serials, sizes and hardware UUID.
   `disposable` explicitly permits reusing the selected disks after authorization;
   it does **not** authorize erasure by itself. Use `fresh` / `new-disks` for empty
   disks, or `migration` / `old-disks` (or `whole-disk-image`) when retaining data.
   Preserve or explicitly re-enroll machine/application credentials even when
   application data is disposable.

2. **Plan on the controller.** Use private absolute paths on encrypted storage:

   ```sh
   devenv shell boot-storage-setup plan --spec <private-spec.yml> --state <state>
   devenv shell boot-storage-setup next --state <state>
   ```

   Planning builds and pins both the system closure and Disko executable.
   Complete the reported recovery checks and record actual evidence through
   `boot-storage-migration attest` as described in the
   [evidence contract](boot-storage-migration.md#guided-operator-workflow).
   The helper never attests to recovery or restore tests on your behalf.

3. **Boot tested installer media on the selected host.** Keep the same clean
   checkout, built Nix paths, state and evidence available at their planned
   absolute paths. State/evidence must be root-owned and private on independent
   encrypted storage, outside `/mnt` and all selected disks. Run the reviewed
   Python environment as root, with no active swap or target mappings/mounts:

   ```sh
   python -m lx_administration.storage.boot_setup advance --state <state>
   python -m lx_administration.storage.boot_setup advance --state <state> --apply
   ```

   The first command previews. The second performs **one** eligible step. For
   provisioning it requires typing the exact host, plan identifier and disk
   serials at a real terminal, then runs the pinned Disko layout. Enter the disk
   passwords at its hidden prompts and preserve them in your password manager.
   It refuses global partition/mapping-name collisions and existing `/mnt`
   mounts. It never formats the running system or automatically reboots.

4. **Prepare credentials and install.** Restore the required original secrets,
   keys, salts and data, or explicitly enroll initial credentials for a disposable
   installation. Review secondary-volume key enrollment and the candidate boot
   password receipt using the detailed guide. Run `advance --apply` to prepare
   missing administrator/initrd SSH access through the existing guarded helper;
   existing credentials are preserved. It does not supply application secrets or
   change account passwords. Complete and attest the reported `prepared` checks.
   Preview again, then `advance --apply` validates the complete target and asks
   for the separate install confirmation. Filesystem identities must still match
   those recorded after provisioning.

5. **Accept the physical result.** Arrange a console-assisted first boot; test
   root unlock, account selection, administrator login/sudo/SSH, application
   startup and decryption, and independent recovery. Keep recovery copies.
   Successful installation alone does not authorize fleet rollout.

### Interrupted setup

Run `next --state <state>` using the same state. A completed format is never
repeated. A running/interrupted provision blocks all automatic retries. Preserve
`provision.json`: it records disk metadata and execution state, **not a backup**.
Inspect the disks; repair/mount the intended complete layout from trusted media,
then preview and explicitly accept it without rerunning Disko:

```sh
python -m lx_administration.storage.boot_setup recover --state <state> --assessor <admin>
python -m lx_administration.storage.boot_setup recover --state <state> --assessor <admin> --apply
```

Recovery rechecks hardware, encrypted filesystems and evidence and requires an
exact terminal confirmation. Incomplete or mismatched layouts remain blocked;
restore retained disks/backups or arrange a separately reviewed reprovision.
For an interrupted installation, follow the existing `install-recovery`
assessment and `boot-storage-migration install --retry-interrupted` procedure.
Never delete journals to bypass a blocked retry. Old boot generations cannot
undo formatting or recover lost keys.

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
