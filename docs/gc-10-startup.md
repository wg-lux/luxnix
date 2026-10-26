# gc-10 automatic startup runbook

Target: `gc-10`, inventory address `172.16.255.110`. Run controller commands
from the durable `/home/admin/luxnix` checkout on gc-02. This procedure prepares
local OpenBao, signed boot and unattended application startup. It is not an
instruction to reinstall, repartition, format containers or repeat migration.

## Current rollout gate

Preparation on 2026-10-26 enables `openbao.local.enable` in gc-10's inventory.
This installs enrollment tools; it does **not** enroll OpenBao or change the
existing `tpm2` unlock selection. Data migration remains disabled.
Do not select `local-openbao` until the enrollment and adoption steps pass.

The live preflight found a TPM, disabled firmware Secure Boot, no measured
UKI, closed storage and inactive PostgreSQL/application. The running generation
does not provide the new enrollment tools. Controller signing custody and
public enrollment files must be created before deployment. These are blockers
to unattended startup, not steps already completed by this runbook.

Validation handoff: inventory rendering and Nix evaluation passed with no
failed assertions; local OpenBao has no boot target until profile adoption.
Nix quality and structure validation passed. The controller then reported
ENOSPC during Devenv GC-root and table-of-contents publication; the full build
was interrupted without a successful result. Documentation contracts passed
25 checks with one stale-TOC failure. Regenerate the TOC and rerun validation
after resolving controller storage. The storage/enrollment owner also requires
final verification of the concurrently changing implementation before deployment.

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
generation: that is not successful deployment. The host must have the
`luxnix-boot-artifacts` import helper available for controller signing; if the
old generation lacks it, resolve that bootstrap prerequisite before attempting
the signing sequence. Do not reboot into a partially installed generation.

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

Change only gc-10's canonical inventory value to
`storage.operatorUnlocked.unlockMethod: '"local-openbao"'`, retaining
`openbao.local.enable: "true"`, `migration.enable: "false"`, both UUIDs and the
`/data/raid01` dependency. Regenerate with the [Autoconf workflow](autoconf.md),
review the gc-10 output, rebuild and sign this new closure, then activate it.
The `openbaoLocalPreflight` check must pass without bypasses.

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
firmware/TPM changes, restore access and reseal through the supported enrollment
procedure; do not overwrite conflicting credentials. A lost OpenBao static
seal key requires its escrowed copy, not merely OpenBao recovery shares.

If console enrollment cannot be completed today, unattended cold startup is
**not ready**. Report that explicitly; leaving an already recovered machine
powered on can preserve availability but is not a substitute for tested boot.
Do not schedule an unattended reboot while these gates remain open.
