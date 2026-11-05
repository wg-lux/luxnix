# gc-02 boot and authentication repair — 2026-11-04

> **2026-11-05 policy update:** desktop autologin is now disabled fleet-wide.
> The shared admin/client guard refuses password-file drift against an existing
> local account; rotation requires explicit confirmation or password entry.
> Earlier host-specific autologin statements and test counts below describe the
> previous candidate. Current policy: `docs/admin-passwords.md` (Explicit
> replacement and activation safety) and `docs/boot-storage-operator.md`.

## Scope and evidence

Source: `/home/admin/luxnix`, branch `lx-annotate_ollama`, starting revision
`6900db128352fb73c878a0cc85e3c4902a42bf89`. The checkout was clean at entry.
`/home/admin/dev/luxnix` is a different, older `main` checkout and was not used.
Target: **gc-02 only**. Shared account and boot module fixes also affect other
consumers; desktop and Vault retry policy changes are host-specific YAML.

The unchanged `flake.lock` SHA-256 is
`65bd23da94a0e9cf17e09ac9c17e8e33e85d55b7fc429d4cca0446e29f62c2f7`.
The Deployment Source Hygiene tracker remains **not production-ready (0/6)**;
this repair does not override its missing fleet acceptance.

The lockfile records every transitive input revision and NAR hash; no inputs were
updated.
| Locked input | Revision |
| --- | --- |
| nixpkgs | `da6dc0e7b26060f2f71ce3ef7088fb56ee44fa36` |
| lanzaboote | `c1c5edd31802d181c8aa2c71588995d93425d650` |
| disko | `725ea35e410ad83be4931d1bff7e090eacaf3563` |
| home-manager | `db7d5e2332710f5abb088f6b5de927d7f9511b35` |

The selected application is LX-Annotate **1.7.5**, wheel SHA-256 SRI
`sha256-TOwNvAA5xkBCN56uXvQnp6wTNNv8PZ3b0mceuD2f+JU=`. The candidate build is
retained at `/home/admin/luxnix/result-gc-02-validation`; record its resolved
closure and `nix path-info --json` NAR identity before installation.

The known-working profile, running system and booted system all resolved to:

```text
/nix/store/r27z05x6h14qh9rnsqjxv1grw13y9j7c-nixos-system-gc-02-26.05.20261021.da6dc0e
```

Firmware boot/default entry was generation **354**. Profiles 352, 353 and 354
were present. No profile, boot entry, firmware key, boot order, LUKS keyslot or
live account credential was changed by the repair. No candidate was activated.

## Findings: confirmed versus unresolved

| Finding | Evidence and consequence |
| --- | --- |
| Shadow is declarative | `host-common.nix` sets immutable users. Both live account hashes matched their private root-owned mode-0600 boot files. `passwd` alone does not persist across activation. |
| Stale client Vault copy exists | Privileged comparison returned `vault_matches_boot=false` for client-user; admin matched. No hashes or passwords were emitted. |
| Unsafe source refresh | `operator_migration.prepare_accounts` previously refreshed existing copies from any different private non-retired Vault hash. A valid stale source could undo explicit recovery. It now preserves existing copies and validates all credentials before initializing absent ones. |
| Missing boot-LUKS preparation wiring | Account preparation was inside the legacy-container condition. The corrected shared enabled-storage path supports fresh boot-LUKS account initialization too. The refresh bug alone is **not proof** of the historic gc-02 lockout: the exact failing generation and its activation log are unavailable. |
| Hidden activation prompt | Admin validation could prompt for replacement during switch/test. It now rejects invalid files without mutation or prompting; rotation is an explicit command. Both users are validated before boot installation as well as account activation. |
| Chooser bypassed | SDDM logged successful client-user autologin without a chooser. gc-02 now selects normal SDDM account login after disk unlock. Physical user switching remains to be accepted. |
| Root storage works | Root is Btrfs on `cryptroot`; the declared `/dev/disk/by-partlabel/luks` identifies the open LUKS2 mapping. Privileged read-only root verification passed. |
| Original FileNotFoundError unresolved | The running helper suppressed the missing pathname. Its declared external dependencies are present and root/mapping probes now pass. The repair checks executable dependencies before staging and reports missing file/executable paths; it does not invent a missing dependency. |
| Secure Boot state | `bootctl status` reported disabled; the current configuration also selects unsigned systemd-boot. A read-only EFI database check found that `conf/secure-boot/db.pem` is **not enrolled**. No firmware setting was changed. The earlier firmware violation cannot be attributed conclusively from this recovered boot. |
| Signing order | Keyless installation previously checked signatures after lzbt. It now requires an enrolled signer and staged signed generations, verifies images before lzbt, and verifies again afterward. Unsigned configurations reject enabled/unreadable EFI Secure Boot state. |
| Application startup stalled | Vault had `offline-cached` status and managed-secret setup failed. TLS health passed using the configured CA. Restarting the existing auth service reached `ready`; starting the existing app succeeded. gc-02 now disables offline auth success, bounds auth startup to 45 seconds, retries failures every 30 seconds, and queues normal app startup asynchronously after successful auth. |
| Shell/GPU freeze unproven | A clean `zsh -lic exit` completed within 12 seconds. Current kernel journal inspection found no OOM/Xid failure. Direnv is enabled in both project shells; no reproducible shell freeze or GPU fault justified changing those modules. |

The application recovery used the **existing generation**. Its normal startup
applied pending migration `endoreg_db.0117_center_shift_presence_fraction`.
LX-Annotate became active/running, port 8117 responded, and nginx returned HTTPS
302 using its deployed self-signed certificate as an explicit trust anchor.
Browser SSO, clinical-media playback and annotation were not exercised. The
separate hub-export health service failed; hub-export acceptance remains open. A system
rollback does not undo that database migration or shared virtualenv state.

## Credential flow

| Credential | Authority and consumer | Rotation/reconciliation |
| --- | --- | --- |
| Root LUKS password | Existing LUKS2 keyslots; local initrd/Plymouth unlock | Ordinary staging verifies only. Explicit `--change` may add a slot with existing authorization and header backup; never removes recovery slots. |
| Admin password | `/var/lib/luxnix-account/admin-password.hash` → immutable users → shadow → login/sudo | Explicit `luxnix-admin-password` or reviewed controller rotation updates the persistent source and live account. |
| Client password | `/var/lib/luxnix-account/client-password.hash` → immutable users → shadow → SDDM/console | Preserve recovered boot hash. An explicit operator rotation must update the persistent file and account together. |
| Controller account pair | Encrypted controller Vault → exported host plaintext/hash files under `/etc/secrets/vault` | Reconcile after local rotation through paired import, validation and export in the admin guide. Ordinary synchronization does not override an existing boot copy. |
| Initial boot copies | `migration.accountHashes`: validated private source only when destination is absent | Existing copies are authoritative. Never delete one to resolve drift. |
| SDDM on gc-02 | Linux password for the selected `admin` or `client-user` | No disk-to-account password synchronization; no autologin. |
| KWallet | Existing wallet password, optionally supplied by password login PAM | A different wallet password needs a separate prompt; account/LUKS rotation does not change it. |
| Boot verification receipt | Machine ID, LUKS UUID and complete header fingerprint | Not a password, key or recovery backup. A changed header invalidates it. |
| Application storage keys and Vault AppRole | Existing protected service files and authenticated Vault runtime | Remain separate from Linux accounts and disk passwords. No rotation, export or fallback was introduced. |

## Verification

Commands run from the source checkout, using its existing `.venv` for Python:

- `nix eval --raw '.#nixosConfigurations.gc-02.config.networking.hostName' --accept-flake-config`: `gc-02`.
- `nix build '.#nixosConfigurations.gc-02.config.system.build.toplevel' --accept-flake-config --out-link result-gc-02-validation`: successful candidate build; the final reviewed revision is rebuilt before handoff.
- Account, disposable LUKS, migration, remote-access and signing regression suite: **178 passed**.
- Updated signing/firmware suite: **25 passed**, including refusal before installer execution and disabled/enabled/missing EFI-state cases.
- Desktop-policy checks: **5 passed**; gc-02 chooser, unchanged other-host autologin, and remote-unlock exclusion.
- The candidate `luxnix-verify-boot-storage` passed read-only on gc-02, and both private boot hashes still validated and matched shadow after application recovery.
- Autoconf validation and isolated render comparison passed; only gc-02 generated output changed.
- Final structure validation passed in both LuxNix and LX-Annotate; both feature trackers validate. The combined documentation, account-policy, chooser and Vault retry checks passed: **68 tests**.

The disposable fresh-install VM initially identified missing `/etc/machine-id`
before receipt staging. The installer procedure and fixture now initialize the
target identity and `/var/lib`, expose installer udev metadata read-only in the
chroot, and verify the actual existing disk password before installation. Without
udev metadata, cryptsetup reports `type: n/a`; that is correctly rejected rather
than accepted as LUKS2.

The first build found a shellcheck regex quoting issue, corrected before the
successful build. Initial test failures exposed missing boot-LUKS account wiring
and a remote-unlock fixture that still enabled autologin; those were corrected
and the full focused suite passed. Full repository Nix quality additionally
reported pre-existing unformatted baseline/log copies and
`modules/nixos/luxnix/storage-access/private-roots.nix`; do not weaken the quality
baseline or modify unrelated historical artifacts to conceal that result. The
commit hook uses nixfmt 1.4.0; changed files were formatted with that version.
The commit attempt was blocked by unrelated existing Ansible lint findings in
`ansible/playbooks/storage-legacy-recovery.yml`,
`ansible/playbooks/storage-local-backup.yml`, and `python-quality.yml`, plus
formatting in `modules/nixos/luxnix/storage-access/private-roots.nix`. Hooks were
not bypassed; reviewed changes remain staged, uncommitted, and unpushed.

`nix build '.#checks.x86_64-linux.boot-storage' --no-link -L` passed. Its
199.96-second test script covered fresh installation, encrypted-root unlock,
a second-generation installation and boot, missing-secondary-key writer
protection, recovery-credential unlock, and final storage verification.

A disposable boot-storage VM is a storage integration check, not physical
Secure Boot, PAM/SDDM or production clinical acceptance. No physical acceptance
is claimed from a build or unit test.

## Follow-up assumption audit

The operator clarified that the failing selection is the **desktop login chooser**,
not the application's annotator selector. The proposed normal SDDM login policy
therefore addresses the intended surface.

The audit found and corrected an additional activation defect: NixOS records
activation-snippet errors but does not enable global `errexit`. A failed
`luxnixPrepareBootAccountHashes` command could therefore continue to subsequent
validators and the user update. Format validation alone does not catch every
preparation refusal (for example, a valid hash behind a rejected symlink).
The preparation wrapper now explicitly exits on failure. A regression executing
the rendered snippet reproduced `USER_UPDATE_REACHED` before the fix and passed
afterward. The focused account/preparation/migration suite passed **154 tests**.

Read-only gc-02 checks additionally established:

- Both accounts are unlocked and unexpired; neither password is expired.
- Both shells and home directories exist, and both shadow hashes still match
  the authoritative boot files. Fresh password-based sudo authentication passed.
- The built user declaration consumes those exact two boot files. SDDM's UID
  range includes both current UIDs; neither account is hidden. No inspected
  KDE user-switch restriction overrides the chooser. Console and desktop keyboard
  layouts are both German (`de`).
- The pinned NixOS switch implementation calls pre-switch checks before its
  bootloader installer for both `boot` and `switch`. The new validators therefore
  protect normal installation; `NIXOS_NO_CHECK` would bypass them and remains
  prohibited by the operator procedure. The rebuilt candidate's native
  `switch-to-configuration check` passed on gc-02 without activation. The
  candidate storage verifier passed, and the existing runtime-environment and
  master-key-check services report successful exit status.
- LX-Annotate, nginx, Vault auth and managed secrets remain active. Verified
  HTTPS returns 302, which proves routing/TLS response, **not authenticated
  clinical functionality**. No systemd failed units were present at this recheck;
  the earlier hub-export health failure is historical, not current acceptance.

The broader Python run produced **251 passes and one test-fixture failure**:
`test_source_cleanliness_and_durable_path_are_required` assumed pytest's temporary
path lived below `/tmp`. This run deliberately used a cache below `/home/admin`.
The test now explicitly supplies `/tmp/disposable-release`, without creating or
using a production source there; all **27 migration tests** passed afterward.
Context/layout tests passed **57 tests** (pytest also warned about cleanup of
unrelated pre-existing temporary directories; no manual cleanup was attempted).

The new `nix build '.#checks.x86_64-linux.boot-recovery' --out-link
result-boot-recovery -L` VM passed the following behavioral checks:

| Assumption | Executed verification |
| --- | --- |
| Offline authentication must not start the application | Application remained inactive with no startup marker until authentication was made available. |
| A later successful retry recovers failed dependency jobs | The real gc-02 `Restart`, timeout and `ExecStartPost` policy, with the relevant evaluated dependency edges, brought up managed secrets and the application without manual dependent-unit restarts. |
| A hanging auth attempt is bounded | The actual 45-second timeout fired; the subsequent 30-second retry recovered the chain. |
| Queuing startup does not restart a healthy app | Repeated start requests left the application start counter unchanged. |
| Account passwords survive stale Vault exports | Actual gc-02 account preparation and validators ran through native immutable-user activation; shadow stayed byte-for-byte unchanged despite different source hashes. |
| Invalid credentials fail before account replacement | Malformed hashes failed pre-switch; a valid hash behind a symlink passed format validation but failed preparation. Both left shadow unchanged. |
| Both accounts authenticate through SDDM PAM | Correct synthetic passwords passed `authenticate` and `acct_mgmt`; wrong passwords failed, before and after reactivation. |
| Normal SDDM displays both users | The actual Breeze/Wayland greeter with gc-02 autologin policy passed screen-recognition checks for `admin` and `client-user`. |

Breeze intentionally hides controls after 60 seconds of idle time. The initial
visual assertion caught the idle wallpaper; inspecting the pinned theme source
confirmed the timeout. The test now sends normal keyboard activity before
checking the chooser and before saving `result-boot-recovery/desktop-chooser.png`.
It does not disable the timeout or weaken the visual assertions.

Test-harness corrections were also required: the generic NixOS VM defaults to
no switch command, so this fixture explicitly enables it; waiting for a future
restart uses polling because `wait_for_unit` rejects an inactive unit with no
currently queued job. Those corrections do not modify production behavior.

Limits remain explicit: the VM uses synthetic credentials, temporary system
disks and fault-injected auth/app processes. It tests the relevant systemd edges,
not the complete production service graph or a real Vault outage. It does not
exercise physical GPU behavior, existing home-directory state, full graphical
session login/logout, firmware-enforced Secure Boot, or clinical workflows.
Other credential providers, including fresh SOPS provisioning, have option-wiring
checks only; their declared boot-copy preparation prerequisites must also be
satisfied. No fleet acceptance follows from this gc-02 audit. A failed native
activation is not transactional: the VM showed subsequent service reloads even
when account preparation aborted, reinforcing the prohibition on live `test`
activation during this repair.

## Implementation references

- `ansible/inventory/host_vars/gc-02.yml` and regenerated
  `systems/x86_64-linux/gc-02/default.nix`: account chooser and bounded Vault retry.
- `modules/nixos/roles/desktop/addons/plasma/default.nix`: explicit
  `bootAutoLogin = false` enforced fleet-wide (supersedes the original host-only policy).
- `modules/nixos/user/admin/default.nix` and
  `modules/nixos/user/client/default.nix`: read-only pre-switch and activation
  validation, explicit admin rotation, client override rejection.
- `modules/nixos/luxnix/operator-unlocked-storage/default.nix`: shared
  `luxnixPrepareBootAccountHashes` wiring for both layouts.
- `lx_administration/storage/operator_migration.py`: `prepare_accounts` preserves
  existing copies; `account_hash` is the shared format/retirement validator.
- `lx_administration/storage/boot_migration.py`: reuses that validator for recovery.
- `lx_administration/storage/boot_password.py`: dependency checks, actionable
  missing-file diagnostics and explicit-only key addition.
- `modules/nixos/system/boot/default.nix`: firmware policy and signature checks
  before installation, retaining post-install verification.
- Regression files: `tests/test_boot_password.py`, `tests/test_boot_storage.py`,
  `tests/test_local_user_recovery.py`, `tests/test_operator_storage_migration.py`,
  `tests/test_remote_boot_access.py`, `tests/test_secure_boot.py`, and
  `tests/nixtest/boot_storage_vm_test.nix`. The follow-up adds
  `tests/nixtest/boot_recovery_vm_test.nix`, extends
  `tests/test_local_user_recovery.py`, and corrects the path fixture in
  `tests/test_boot_migration.py`; `flake.nix` and `tests/structure.yml` expose
  and document the new VM check.
- Runbooks: `docs/admin-passwords.md`, `docs/boot-storage-migration.md`,
  `docs/boot-storage-operator.md`, and this report. Navigation/context updates:
  `docs/structure.yml`, `mkdocs.yaml`, regenerated `TABLE_OF_CONTENTS.md`.

## Operator installation procedure — requires separate approval

1. Keep the working root/sudo session and an independently verified SSH-key
   connection open. Have local console and trusted recovery media available.
   Retain generation 354 and its closure; do not run generation cleanup or GC.
2. Review the final commit, clean status and unchanged lockfile at
   `/home/admin/luxnix`. Rebuild the exact reviewed source with the command above.
   Record the resolved candidate closure and its NAR hash. Stop on any failure.
3. Confirm both boot hashes still match shadow without printing them. Validate
   root-owned 0400/0600 files and independent SSH keys. Do **not** copy the stale
   client Vault hash over the recovered boot copy or use `passwd` alone.
4. Review `bootctl status`, enrolled public signing identity, available ESP space
   and existing entries. If firmware Secure Boot is enabled, do not install this
   unsigned profile: use the established controller signing workflow bound to
   the existing enrolled identity. Do not enroll replacement keys or disable
   enforcement. Signing success, installation, physical boot and login are
   separate acceptance gates.
5. In a private local terminal, run the **candidate's** helper:

   ```sh
   sudo /home/admin/luxnix/result-gc-02-validation/sw/bin/luxnix-setup-boot-password
   ```

   Enter the existing disk password only. Do not use `--change` for this repair.
   Stop if staging fails; retain the diagnostic and do not reboot.
6. Only after explicit installation approval and all gates pass, use the
   documented native `nixos-rebuild boot` workflow against this reviewed source
   and gc-02. Never use `NIXOS_NO_CHECK`, an old PATH helper, or `test` activation.
   Check command success, system-profile closure, bootloader default and preserved
   generation 354. If installation fails, stop and inspect all three independently;
   a system-profile change is not proof of bootloader success.
7. Reboot only in a separately approved maintenance window. Confirm root unlock
   with networking disconnected, the account chooser, fresh admin and client
   logins, sudo and independent SSH. Reconnect networking and require Vault
   `ready`, managed secrets success, LX-Annotate active, and verified HTTPS.
   Exercise SSO, old encrypted media, annotation and logout/user selection.
   Check the Vault retry when connectivity is delayed; a healthy app must not
   restart merely because its start is queued again.

## Rollback and recovery

Before reboot, retain the running generation and stop on any failed gate. After
an unsuccessful candidate boot, choose **354** from the firmware/systemd-boot
menu with console access. Do not delete the failed generation or logs before
inspection. Check that its application package remains compatible with the live
database; never bypass the migration/downgrade guard or assume a NixOS rollback
restores application state.

If login fails, use the independent SSH key/root session or trusted NixOS Minimal
media. Identify the existing disks and open the existing LUKS mappings using
retained credentials; never format, recreate containers, remove keyslots or
invent replacement keys. Mount the installed root following its recorded layout.
Inspect the selected generation's configured hash paths and preserve existing
files before any explicitly approved repair. Restore the recovered authoritative
boot credential, ownership and mode together with shadow under the reviewed
account procedure. A `passwd` change alone is temporary with immutable users.
A failed PAM operation inside `nixos-enter` does not prove that a password is
wrong; acceptance requires a real boot and fresh login.

Keep controller reconciliation, wallet changes, application-key recovery and
LUKS rotation separate. Firmware rejection requires checking the existing
signer/loader/generation chain; do not reset keys or turn off Secure Boot as a
recovery shortcut.
