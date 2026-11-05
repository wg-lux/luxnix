# Root encryption: operator steps

This process replaces a disk layout; it does not encrypt the running system in
place. A rebuild or reboot cannot perform the conversion. If you only need to
understand the next step, use **Preview** and stop there.

Before continuing, check the displayed **computer name, disk serials and data
policy**. `migration` requires backup and restore verification; `disposable`
allows erasing existing files **without a data backup check**; `fresh` is for
empty new disks. If you need existing data, or do not know, stop and have an
administrator prepare a migration plan. Never change the mode simply to skip a
failed check. A backup of gc-10 is not a backup of gc-09.

The workflow does not create your data backups. Someone must actually test the
required recovery and restore steps. If you do not understand a check, stop and
ask for help; do not type `VERIFIED`. Never put passwords in chat or notes.

## 1. Preview — installed host, normal user

- Connect the recovery drive.
- Use the updated, reviewed, clean LuxNix checkout configured in `autoconf/config.yml`.
- Check the configured host, hardware UUID and target disk serials.

```sh
devenv tasks run boot-storage:setup
```


## 2. Prepare recovery — same terminal

```sh
LUXNIX_BOOT_SETUP_APPLY=1 devenv tasks run boot-storage:setup
```

- Complete the displayed recovery checks; preserve credentials and required backups.
- Write the requested `<stage>-notes.txt` with mode `0600`, without secrets.
- Rerun the command and confirm only checks you actually performed.
- Before leaving: preserve the reviewed checkout, pinned Nix artifacts and recovery
  journal independently of the disks to be erased, at their planned paths.

## 3. Install — trusted installer media, root terminal

- Boot the tested NixOS installer; mount the recovery filesystem at `/recovery`.
- Make the preserved checkout, Nix artifacts and reviewed Python environment available.
- Ensure recovery state/evidence is root-owned and private; disable active swap.
- From the preserved checkout, run:

```sh
python -m lx_administration.storage.boot_setup run --current-host --apply
```

- Confirm the exact target disk serials before erasure; enter and save the LUKS password.
- This is the destructive step. The prompt requires the computer name, plan ID
  and disk serials; `yes` or an empty answer cancels. An old boot generation cannot
  recover erased files.
- Supply the requested credentials and completed prepared-stage notes.
- Rerun after each requested action; confirm installation separately.
- If interrupted, stop and follow [recovery instructions](boot-storage-migration.md#interrupted-setup).
  Keep the journal; do not restart formatting.

Do not run `sudo devenv` to get past an installer warning. The installed system
and installer use different commands deliberately. Keep the recovery drive
connected and never erase or repurpose it during this procedure.

## 4. Cold boot and accept

- After successful installation, boot the installed system.
- Test root unlock, desktop user selection, admin login/sudo/SSH and application decryption.
- Write the requested acceptance notes; retain the recovery drive and credentials.
- With recovery state private and owned by the operator running the workflow, rerun:

```sh
LUXNIX_BOOT_SETUP_APPLY=1 devenv tasks run boot-storage:setup
```

Do not use `nh os boot` to convert plaintext root. Keep the planned release unchanged.
For installer handoff requirements, see the [detailed guide](boot-storage-migration.md#configuration-and-recovery-media).
