# gc-10 automatic startup runbook

Target: `gc-10`, inventory address `172.16.255.110`. Run controller commands
from the durable `/home/admin/luxnix` checkout on gc-02. This procedure prepares
local OpenBao, signed boot and unattended application startup. It is not an
instruction to reinstall, repartition, format containers or repeat migration.

## Current rollout gate

### Local Backup export exception

The operator explicitly authorized unencrypted local annotation export copies
on gc-10's existing Backup disk. This exception applies only to
`/var/lib/lx-annotate/data/storage/frame_annotation_exports`, bound from
`/run/media/admin/Backup-24-11/lx-annotate-exports`; imports, keys, database
storage and other hosts retain their existing boundaries. Scope and evidence
remain in `feature-tracking/lx_annotate_environment_lifecycle_audit.yaml`,
criterion `gc10_local_backup_exports`.

The host-owned `backup-exports.nix` mounts the existing filesystem by UUID,
verifies its identity before creating the service-owned child, and activates
the bind on access. Missing media fails export access without writing to the
application disk. It neither formats the disk nor changes its existing mount
path. Prepare an empty root-owned mode `0500` target under the unlocked
application storage before first activation; never hide or move existing
exports implicitly. The bind mount hides that nonwritable underlying directory.

On first adoption, an existing temporary bind at the export path prevents the
automount from starting and can block web and FFmpeg worker startup. Confirm
that no export is running and keep those consumers stopped while replacing
the temporary bind. On gc-10, stop only the export mount, start its automount,
then start the consumers:

```sh
sudo systemctl stop 'var-lib-lx\x2dannotate-data-storage-frame_annotation_exports.mount'
sudo systemctl start 'var-lib-lx\x2dannotate-data-storage-frame_annotation_exports.automount'
sudo systemctl start --no-block lx-annotate.service lx-annotate-celery-ffmpeg-worker.service
```

Do not unmount the Backup filesystem, move export files, or force an unmount.
If the export mount is busy, stop and identify its active consumer first.
Check both service states and confirm the automount is active before resuming
exports; `--no-block` only schedules startup and does not prove readiness.

Review both the Backup mount and export mount with `findmnt` before exporting.
Stop export activity before removing the disk. After reconnecting, clear a
failed `gc10-backup-exports-prepare.service` and export mount with
`systemctl reset-failed`, then retry access. Do not stop the export automount
while application consumers run. Ordinary startup does not require the disk
until an export accesses its path. The external copies are plaintext and must
remain under the operator's local physical control.

### Encrypted application startup

For the current operator-controlled profile, use
[local OpenBao enrollment and password guidance](openbao-local.md#passwords-initial-enrollment-and-resets)
and [storage startup](operator-unlocked-storage.md#boot-with-operator-passphrase-unlock).
Installing the OpenBao tool does not set a password. Direct LUKS passphrases,
the OpenBao boot passphrase and the administrator password are separate.
There is no implemented OpenBao passphrase-reset command; `rotate-unlock`
rotates an AppRole SecretID. Inspect live status before deciding whether initial
enrollment or recovery is required. gc-10 follows the common EndoReg passphrase
seal profile, with no host-specific exception.

**Production unattended rollout is blocked.** Follow R0-R5 in
`boot-encryption-acceptance.yml`; gc-10 is a reference for its hardware class,
not an exception to the group profile. Sections 1-5 below describe a future
procedure after those gates pass. They do not authorize enrollment, keyslot
changes, activation or reboot now. Signed boot without authenticated root/Nix
contents cannot satisfy ENC-09. The future procedure below assumes an accepted
group TPM-seal profile; it must not be executed unchanged with the current
`seal = "passphrase"` default. The current role still rejects unattended unlock.

Before firmware or credential changes, verify the effective live unlock method
(`passphrase` versus an older `tpm2` generation), booted/current/profile targets,
Secure Boot state and intended enrolled-key fingerprints. Inventory existing
TPM credentials, LUKS slots/UUIDs and recovery references without exporting
secret values. Preserve the known-working unlock path until acceptance.

Preparation on 2026-10-26 enables `openbao.local.enable` in gc-10's inventory.
This installs enrollment tools; it does **not** enroll OpenBao. Since
2026-10-27 the repository configures gc-10 for operator passphrase unlock like
the rest of the fleet, with Secure Boot disabled by default; the steps below apply only once TPM unlock is
resumed. Data migration remains disabled.
Do not select `local-openbao` until the enrollment and adoption steps pass.

Historical preparation observations from 2026-10-26 (not current live status):
the preflight found a TPM, disabled firmware Secure Boot, no measured
UKI, closed storage and inactive PostgreSQL/application. The running generation
did not provide the new enrollment tools. Controller signing custody and
public enrollment files were subsequently created by the operator. Recheck
the running generation, tools and enrollment before using this procedure.

Validation resumed on 2026-10-26 after controller storage cleanup: the table
of contents was regenerated, all 26 documentation checks passed, and Nix quality
and structure checks passed. Public signing material is now provisioned; the
operator confirmed independent archive and passphrase custody. The full build,
physical enrollment and boot acceptance remain required before activation.

PCR 7 binding and signed boot do not authenticate the writable root/Nix store.
ENC-09 remains a separate release blocker: this procedure alone does not prove
protection against offline modification of a stolen machine. Do not mark the
fleet encryption acceptance catalog complete after a successful boot.

## Preserve recovery and identify the data

| Volume | Existing container | Required LUKS UUID |
| --- | --- | --- |
| luxnix-app-storage | `/data/raid01/luxnix-app-storage.luks` | `f5869d54-4ea5-407c-a690-7238fe79cd6b` |
| luxnix-secrets | `/var/lib/luxnix-secrets.luks` | `dc53d362-e6e2-43ee-9cbf-4726d55c3055` |

Keep the original storage and encrypted rescue container until recovery and
cold boot are accepted. Never remove a container to resolve an unlock error.
Keep current application master keys, salts and database together; successful
filesystem unlock does not prove application decryption or completed import.

Recovery custody is the encrypted admin vault on gc-02 (`~/.lxv`) and an
independent encrypted export on gs-02 (`~/.luxnix-recovery`). The controller's
vault key must also have an independently recoverable custody arrangement;
ciphertext alone is not recovery. Do not copy its plaintext key to gc-10.
This recorded layout still depends on gs-02 for the emergency export. Before
R0 passes, verify an additional encrypted recovery copy outside both gs-02 and
gc-10, including the local seal trust anchor and independently recoverable keys.
No such copy was verified in this planning update.

Private controller inputs are `/home/admin/pwd_gc-10.txt` for sudo,
`/home/admin/Desktop/token-gc-10-enc.txt` for application-container recovery,
and `/home/admin/Desktop/token-gc-10.txt` for secrets-container recovery.
These files remain private and are not boot dependencies or repository inputs.

## 1. Validate and sign the exact deployment

```bash
devenv tasks run autoconf:check
nix eval .#nixosConfigurations.gc-10.config.system.build.toplevel.drvPath
nix build .#nixosConfigurations.gc-10.config.system.build.toplevel --no-link
devenv tasks run nix-quality:check docs:check
python scripts/lint_structure.py
devenv shell check-connectivity gc-10
devenv shell check-connectivity gs-02
```

Record the reviewed revision, working-tree changes, `flake.lock`, built store
path and previous host system/boot profile. Referenced new source files must be
included in the Git index for a Git-flake build. Never substitute another
checkout after building. A failing build or pre-switch check is a stop gate.

Use [controller signing](secure-boot.md) to create the fleet PKI from a private
interactive terminal (`devenv shell secure-boot-keys`). Its passphrase is entered
there, never in chat. Verify independent encrypted custody before proceeding;
publish only `db.pem`, `PK.auth`, `KEK.auth` and `db.auth` in `conf/secure-boot`.
Rebuild after adding those public files, since they change the closure.

Follow the [deployment workflow](deployment-guide.md) to stage this exact
gc-10 closure, then `devenv shell secure-boot-sign gc-10` and finish the boot
installation as documented. The first keyless install can refuse an unsigned
generation: that is not successful deployment. Controller signing invokes the import helper from the exact new system
closure, which verifies against its build-time public certificate. This works
before the old system has the helper or the new `/etc` tree. Do not reboot into a partially installed generation.

## 2. Enroll firmware, then local OpenBao

With physical/BMC console recovery available, follow
[firmware enrollment](secure-boot.md#per-host-firmware-enrollment): verify the
signed ESP, enter firmware setup mode, run the guarded enrollment helper, and
enable Secure Boot. Reboot and verify `bootctl status` reports enabled Secure
Boot and the intended signed generation. Do not seal credentials against the
old disabled-Secure-Boot PCR policy.

From gc-02, after the new tooling is installed:

```bash
devenv shell openbao-local status --limit gc-10 \
  --sudo-password-file /home/admin/pwd_gc-10.txt
devenv shell openbao-local enroll --limit gc-10 --recovery-host gs-02 \
  --sudo-password-file /home/admin/pwd_gc-10.txt
devenv shell openbao-local enroll --limit gc-10 --recovery-host gs-02 \
  --sudo-password-file /home/admin/pwd_gc-10.txt --apply
```

Enrollment must escrow the seal key and recovery/provisioner credentials in
both locations, prove TPM decryption, confirm escrow, and revoke the initial
root token. Use [resumption guidance](openbao-local.md#interrupted-initialization)
if interrupted. Never delete Raft state to make enrollment pass.

## 3. Adopt existing volumes without moving data

Revalidate both existing recovery records using the cataloged escrow command:

```bash
devenv shell storage-provision escrow --host gc-10 --volume luxnix-app-storage \
  --recovery-host gs-02 --sudo-password-file /home/admin/pwd_gc-10.txt \
  --existing-key-file /home/admin/Desktop/token-gc-10-enc.txt --apply
devenv shell storage-provision escrow --host gc-10 --volume luxnix-secrets \
  --recovery-host gs-02 --sudo-password-file /home/admin/pwd_gc-10.txt \
  --existing-key-file /home/admin/Desktop/token-gc-10.txt --apply
devenv shell openbao-local adopt --limit gc-10 --recovery-host gs-02 \
  --sudo-password-file /home/admin/pwd_gc-10.txt
devenv shell openbao-local adopt --limit gc-10 --recovery-host gs-02 \
  --sudo-password-file /home/admin/pwd_gc-10.txt --apply
```

Require the declared UUIDs, a tested OpenBao slot and a tested recovery slot
for both volumes. Adoption removes direct `systemd-tpm2` slots only after the
OpenBao key works. Do not run legacy `enroll-tpm2` afterwards. Do not restart or
reboot between adoption and the following profile switch: the old TPM unlock
policy will no longer match the adopted volumes.

## 4. Enable unattended startup

After R1-R4 and the required human assessments pass, prepare the bounded R5
inventory wave using the same accepted group profile. Do not introduce a gc-10
host-only `local-openbao` override. Every selected host must have verified
enrollment, recovery, declared UUIDs and adoption/provisioning before switching;
keep remaining hosts on operator unlock until the group change is safe.
Use canonical YAML inputs and the [Autoconf workflow](autoconf.md), review
rendered outputs, build and sign the exact closure, and require
`openbaoLocalPreflight` without bypasses. Preserve gc-10's disabled migration,
existing UUIDs and `/data/raid01` dependency. A group-default change remains
blocked while any affected host is unprepared.

Normal boot then starts local OpenBao, releases UUID-bound volume keys,
opens LUKS, mounts the guarded paths and starts application dependencies.
Neither the controller nor hub OpenBao should be needed to release these
volume keys. Application identity and transfer services may still need the
hub. Do not migrate the hub identity backend as part of this host rollout.

## 5. Prove startup before relying on it tomorrow

On gc-10, inspect the [startup chain and intake diagnostics](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/services/lx-annotate-local/Diagnostics.md).
Do not dump environment files, tokens or database patient records into logs.

```bash
bootctl status --no-pager
readlink -f /run/current-system
readlink -f /nix/var/nix/profiles/system
sudo systemctl is-active openbao-local.service postgresql.service lx-annotate.service
sudo systemctl list-units 'luxnix-storage-*' 'lx-annotate*' --all --no-pager
findmnt /var/lib/luxnix-app-storage
findmnt /var/lib/luxnix-secrets
findmnt /var/lib/lx-annotate
findmnt /var/lib/postgresql
sudo systemctl --failed --no-pager
```

Verify both source devices are the expected dm-crypt mappings, encrypted
application storage checks pass, HTTPS serves the login page/static files,
required Celery workers and the filewatcher are active, and the existing
import has its expected database state and accessible encrypted media. A
running web process alone is insufficient. Do not requeue or duplicate the
import merely to test startup.

With console recovery present, perform a controlled reboot and repeat these
checks before any manual unlock or start command. Require
`/run/booted-system`, `/run/current-system` and the intended profile to agree.
Inspect the boot default and one-shot overrides, not only the running profile.
Finally perform a power-off/cold-start test with no password entry. Record the
selected generation, successful automatic unlock, mount sources and app checks.
Only those observed results justify saying gc-10 will start unattended.

## Failure and overnight handoff

If signing, firmware enrollment, escrow, adoption or preflight fails, stop at
that phase and preserve the previous signed boot entry, containers and Raft
state. Do not disable Secure Boot checks, add plaintext boot keys or format a
replacement volume. A NixOS generation rollback does not undo keyslot changes;
after adoption an old direct-TPM profile may require explicit recovery.

Use the retained container recovery passphrases from a private console and the
documented [storage recovery workflow](operator-unlocked-storage.md). After
firmware/TPM changes, restore access through verified recovery custody and a
separately reviewed resealing procedure. Automated recovery/re-seeding remains
unimplemented; ordinary enrollment does not overwrite conflicting credentials.
A lost OpenBao static
seal key requires its escrowed copy, not merely OpenBao recovery shares.

If console enrollment cannot be completed today, unattended cold startup is
**not ready**. Report that explicitly; leaving an already recovered machine
powered on can preserve availability but is not a substitute for tested boot.
Do not schedule an unattended reboot while these gates remain open.
