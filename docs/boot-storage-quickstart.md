# Root encryption: operator steps

Hosts with data use `installation: in-place`: the root partition is encrypted where
it is, from installer media, and nothing is formatted. A rebuild or reboot cannot
perform the conversion. If you only need to understand the next step, use **Preview**
and stop there.

**Make and test a backup first.** A power cut can be resumed, but bad RAM or a failing
disk during the conversion can damage data. Old unencrypted copies can also stay
physically readable on SSD flash, so a host that ever stored patient data on its
plaintext root needs a separate data-remanence review; this tool does not securely erase old data.

Before continuing, check the displayed **computer name and disk serials**.
Only `installation: in-place` and `source_retention: in-place` are supported.
The former erase/restore, fresh and disposable modes are retired. Old plans
cannot execute; preserve their journals and backups for recovery review.
Unsupported layouts stop without offering a formatting fallback.

The workflow does not create your data backups. Someone must actually test the
required recovery and restore steps. If you do not understand a check, stop and
ask for help; do not type `VERIFIED`. Never put passwords in chat or notes.

## 1. Run the one command — installed host, normal user

Connect the recovery drive, use the reviewed clean checkout, then run this. It works
out the host from this machine's name or hardware UUID, and you can stop and rerun it
at any point, including after a reboot:

```sh
devenv shell boot-storage-setup
```

It does this for you:

- Before there is a plan, shows how this host gets its identity salt and recommends its
  own random salt, which the hub never holds. See [choosing the salt](center-identity-salt-activation.md#choosing-the-salt-at-first-setup).
- Mounts the recovery drive and saves the plan. If the checkout changed and the plan
  has not started, it offers to replace the plan and keeps the old one.
- Opens encrypted custody, or creates it after you type `CREATE CUSTODY`. It never
  formats an existing custody file.
- Copies the secrets missing from custody after you agree, proves they survive closing
  the volume, and runs preflight.
- Searches the unencrypted root for likely patient files, checks the backup is on
  another disk, and writes the notes and the review for you.

## 2. Confirm what only you can prove

The command asks for these one at a time and remembers your answers for 24 hours. Type
`VERIFIED` only for what you did, or press Enter to stop for now.

- A data backup exists and you tested restoring it. The tool creates no backup.
- Patient data was never on the unencrypted root. The search cannot prove this: if it
  ever was, stop for a data-remanence review.
- The custody passphrase and your credentials are kept off this computer.
- The physical console, keyboard and firmware boot menu work.
- The trusted installer boots here and sees both drives. Boot back and rerun the command.

Each step that works prints a `SUCCESS:` line, a progress checklist shows whether root
is encrypted yet, and `Root setup stopped:` means that command did not finish. To look
without changing anything, run `devenv tasks run boot-storage:setup`.

Before leaving: preserve the reviewed checkout, pinned Nix artifacts and recovery
journal independently of the disks being converted, at their planned paths.

## 3. Install — trusted installer media, root terminal

- Boot the tested NixOS installer; mount the recovery filesystem at `/recovery`.
- Make the preserved checkout, Nix artifacts and reviewed Python environment available.
- Ensure recovery state/evidence is root-owned and private; disable active swap.
- From the preserved checkout, run:

```sh
python -m lx_administration.storage.boot_setup run --apply
```

- Confirm the exact target disk serials before encryption; enter and preserve the LUKS password.
  It may use only letters a-x, digits and spaces, because the boot prompt can use a
  different keyboard layout.
- The conversion preserves the filesystem. Type the displayed `ENCRYPT IN PLACE` line
  with the computer name, plan ID and disk serials; `yes` or an empty answer cancels.
  A tested backup is still required because hardware failure can damage data during
  conversion.
- Supply the requested credentials and completed prepared-stage notes.
- Rerun after each requested action; confirm installation separately.
- If interrupted, stop and follow [recovery instructions](boot-storage-migration.md#interrupted-setup).
  Keep the journal and rerun the same command; it resumes.

Do not run `sudo devenv` to get past an installer warning. The installed system
and installer use different commands deliberately. Keep the recovery drive
connected and never erase or repurpose it during this procedure.

## 4. Cold boot and accept

- After successful installation, boot the installed system.
- Test root unlock, desktop user selection, admin login/sudo/SSH and application decryption.
- Write the requested acceptance notes; retain the recovery drive and credentials.
- With recovery state private and owned by the operator running the workflow, rerun:

```sh
devenv shell boot-storage-setup
```

Do not use `nh os boot` to convert plaintext root. Keep the planned release unchanged.

## 5. Remove the old containers

Only after acceptance is recorded, on the installed system. It asks for `sudo` itself.
Without `--apply` it only previews; with it, typed approval deletes the container files
permanently.

```sh
devenv shell boot-storage-setup retire-containers
devenv shell boot-storage-setup retire-containers --apply
```

For installer handoff requirements, see the [detailed guide](boot-storage-migration.md#configuration-and-recovery-media).
