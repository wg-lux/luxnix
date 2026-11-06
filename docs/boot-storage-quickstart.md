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

The task display can garble or cut off this output. To read the full instructions, run
`devenv shell boot-storage-setup next --host <host>`, using the real host name.

- Complete the displayed recovery checks; preserve credentials and required backups.
- Write the requested `<stage>-notes.txt` with mode `0600`, without secrets.
- Rerun the command and confirm only checks you actually performed.
- Before leaving: preserve the reviewed checkout, pinned Nix artifacts and recovery
  journal independently of the disks being converted, at their planned paths.

## 3. Install — trusted installer media, root terminal

- Boot the tested NixOS installer; mount the recovery filesystem at `/recovery`.
- Make the preserved checkout, Nix artifacts and reviewed Python environment available.
- Ensure recovery state/evidence is root-owned and private; disable active swap.
- From the preserved checkout, run:

```sh
python -m lx_administration.storage.boot_setup run --current-host --apply
```

- Confirm the exact target disk serials before encryption; enter and preserve the LUKS password.
- The conversion preserves the filesystem. The prompt requires the computer name,
  plan ID and disk serials; `yes` or an empty answer cancels. A tested backup is
  still required because hardware failure can damage data during conversion.
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
