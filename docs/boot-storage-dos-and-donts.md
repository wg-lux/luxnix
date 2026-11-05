# Boot and storage: dos and don'ts

Rules learned from the fleet audit (2026-11-03), the
[gc-02 boot repair](guides/gc-02-boot-repair.md), the
[gc-10 applicability review](guides/gc-10-boot-applicability.md) and the gc-09 and gc-10
boot failures. Procedures live in the
[operator checklist](boot-storage-operator.md) and the
[migration reference](boot-storage-migration.md).

## Establish what is actually running

**Do**

- Compare the configuration with the live disks before any rebuild. A host can
  evaluate as `boot-luks` while its root is still plaintext; gc-09 and gs-02 did.
- Identify a generation by its full store path, and confirm a reboot from uptime
  and `/run/booted-system`. A `sudo reboot` on gc-09 had not taken effect.
- Check which file defines a failing unit:
  `systemctl show <unit> -p FragmentPath`. On gc-10, nine old `.mount` files in
  `/etc/systemd/system.control` overrode the correct generated units.
- Record operator reports and independent checks separately. A refused SSH login
  says nothing about the state of the host.

**Don't**

- Don't read a date from a system store path as its build date. It is the nixpkgs
  release date.
- Don't blame shared module logic until you have checked for host-local overrides.
  The gc-10 stall first looked like a systemd ordering problem; it was stale units.
- Don't trust `findmnt <path>` or an "active" mount unit alone. On gc-09 a parent
  mount hid `/etc/secrets/vault`, and both still looked healthy. Use `mountpoint`.

## Deploy and activate

**Do**

- Build the exact target from a clean, reviewed checkout, and record its revision,
  lockfile and closure.
- Keep the last known-good generation, console access and an independent SSH
  session until the new boot is accepted.
- Check the command result, system profile and bootloader default separately.
  A profile change does not prove the bootloader was updated.
- Accept a boot only after a real reboot: unlock, mounts, fresh logins, services
  and the application.

**Don't**

- Don't deploy from a dirty checkout, a checkout under `/tmp` or an older clone.
- Don't use `test` activation as a rehearsal. On gc-10 it installed a newer
  application while the boot entry kept the older one, and the reboot then hit the
  downgrade guard.
- Don't assume a NixOS rollback restores the application. It doesn't undo database
  migrations or shared runtime state.
- Don't treat `nixos-rebuild boot` succeeding as a healthy reboot.
- Don't clean up generations or run garbage collection during a repair.

## Encrypted storage

**Do**

- Use one model: LUKS2 root, then Btrfs. With RAID: disks, MD, LUKS2, filesystem.
- Pin a host to `legacy-containers` with migration off if it must keep its existing
  disks, and record the owner decision in `boot-encryption-acceptance.yml`.
- Treat any secret that ever sat on a plaintext root as exposed. Rotate it, and
  erase the old copy only after verifying the encrypted one.
- Retire stale `system.control` units with `luxnix-normalize-storage`, with writers
  stopped. Preview first, then `--apply`.

**Don't**

- Don't expect a rebuild to encrypt a disk. That takes a console-attended
  reprovision and a tested restore.
- Don't bypass the pre-switch check with `NIXOS_NO_CHECK=1`. The machine would wait
  for a LUKS volume that doesn't exist.
- Don't weaken a failing storage assertion. It stops writers from using unprotected
  paths; fix the mount instead.
- Don't mount a container over a live path with migration off. It hides the live
  data, which for Vault storage would mean an empty Vault.
- Don't delete all of `system.control`, format, recreate containers or remove
  keyslots to get past a boot failure.
- Don't count RAID as a backup.

## Passwords and accounts

**Do**

- Keep disk unlock, Linux login, KWallet and application keys as separate credentials.
- Rotate account passwords only with the explicit commands, so the persistent hash
  and the live account change together.
- Keep independent recovery credentials off the machine they recover, and test them.
- Test a stored key against the LUKS header before relying on it. On gc-10 the key
  file's exact bytes failed; the same credential without its final newline worked.

**Don't**

- Don't enable desktop autologin. It is rejected fleet-wide.
- Don't use `passwd` alone. Accounts are declarative, so activation overwrites it.
- Don't delete a boot account copy to resolve drift, or overwrite a recovered one
  from a stale Vault copy. gc-02 had one.
- Don't activate against a missing, stale or retired password hash.
- Don't disable Secure Boot or enroll new keys as a recovery shortcut.

## Application, salts and backups

**Do**

- Check that a release actually imports before pinning it. `lx_annotate` 1.7.3 pinned
  `endoreg-db` 1.7.8 exactly, and the pair failed with `ImportError` at startup.
- Require Vault to report `ready`. On gc-02 `offline-cached` left managed secrets
  failing and the application stopped.
- Resolve a failed identity-salt migration through its review file. On gs-02 it
  stopped by design on records with incomplete source identity.
- Test restores of coupled database, application data and keys.

**Don't**

- Don't replace or regenerate identity salts to clear a failure.
- Don't count a successful timer or SQL dump as proof of recovery. gs-02's PostgreSQL
  dump succeeded while its hub backup failed.

## Roll out and verify

**Do**

- Build one pinned release centrally, prove it on a canary client, then roll out
  through the clients and finish with the hub.
- Schedule reboots for when someone can unlock the disk.
- Read a test's actual result. An instant `nix build` with no output reused an
  earlier result; `nix log <drv>` shows what that run did.
- Check locks and `git status` before editing shared files, as several agents may
  work in this tree.

**Don't**

- Don't enable scheduled updates that track a branch or use `switch`. Use a reviewed
  commit and `boot`.
- Don't treat a VM test as physical acceptance. It proves the Plymouth prompt wiring,
  not a host's graphics or keyboard at the splash.
