# Credential backup before root migration

This command saves **credentials**, not PostgreSQL data, media, a full home
directory or a complete Vault server. It never changes passwords, deletes files,
formats a drive or approves erasure. Keep the original disk and recovery copies
until the restored installation is accepted.

## What is preserved

The immutable boot plan's secret contract supplies application master keys,
identity salts/keyrings, VPN and SOPS identities and selected account hashes.
The command additionally evaluates the declared account initialization sources,
SSH host keys, Vault directory and secret root from that same release. It
preserves the controller's `.lxv` and `.lxv.key` if present in the evaluated admin
home, plus the optional paths in `credential-backup-policy.yml`. Missing required
files, locked storage, symlinks and special files stop the backup for review.
All regular files under included directories are retained, including potential
retirement candidates. There is no automatic deletion or credential generation.

| Account | Authoritative boot copy | Initialization source |
| --- | --- | --- |
| Admin | evaluated `users.users.<admin>.hashedPasswordFile`, normally `/var/lib/luxnix-account/admin-password.hash` | `migration.accountHashes` normally points to `luxnix.vault.adminPasswordHashedFile` |
| Client, when enabled | evaluated `users.users.<client>.hashedPasswordFile`, normally `/var/lib/luxnix-account/client-password.hash` | normally `${luxnix.vault.dir}/SCRT_client_user_password_hash` |

Both copies are saved. The live account must match its boot hash; the Vault
initialization copy can be stale and must not overwrite the boot hash during
restore. `devenv shell rotate-admin-passwords` invokes
`ansible/playbooks/rotate_admin_passwords.yml`: it updates the Vault pair, boot
copy and live shadow entry after validating the replacement. The local
`sudo luxnix-admin-password` command changes the boot hash and live account and
updates Vault copies only when their storage is encrypted. Neither command is a
backup operation. Do not run either merely to prepare this backup.

`scripts/find-password-paths.sh` is a discovery aid, not proof that a file is
unused. Its `UNUSED` group includes `/etc/user-passwords`, old `*_hashed` files,
the plaintext `SCRT_client_user_password`, old PostgreSQL main/test password
exports and retired nginx/MinIO exports. These may be retired **only after**
checking the selected host's evaluated consumers, current and retained recovery
generations and a tested restore. Never retire the active admin/client hashes,
`endoregDbLocal.password`, application keys/salts, controller Vault/key or keys
needed by retained containers. A re-exportable credential is not automatically
safe to delete when its controller or VPN might be unavailable.

## Prepare the destination and unlocking key

Use a reviewed clean checkout and a matching boot plan with `secret_contract`.
The helper runs locally on the selected host and checks its hardware UUID.
Run Devenv as your normal user; its wrapper invokes the reviewed helper through
sudo. Planning/building the candidate and preserving the release remain separate.

The backup drive must already be mounted. Create a **root-owned mode-0700
directory** there using your normal reviewed media-preparation procedure. It
must be physically independent of the selected disks and credential sources.
The drive may be plaintext: only age ciphertext is written to it. No plaintext
archive or credentials are staged on disk. Disk swap must be encrypted or
disabled; core dumps are disabled in the helper.

Supply an existing native age identity from **separate encrypted physical
storage**, independent of both the backup drive and disks being erased. The
command refuses a key on those disks. This is the archive unlocking key, not an
admin password, SSH login key or LUKS master key. Provision and test independent
key custody using the existing `storage-recovery-custody` workflow first. Do not
store the only copy of that key in the archive it must decrypt.
The identity and its parent directory must be root-owned and private for this
sudo-operated command; custody created as another user needs a separately
reviewed root-owned copy on that encrypted medium.

The following paths are examples to replace with your verified locations. A new
archive name is required for every backup; existing files are never overwritten:

```sh
devenv shell credential-backup preview \
  --state /recovery/luxnix-state/gc-09 \
  --archive /recovery/credential-backups/gc-09-2026-11-06.tar.age

devenv shell credential-backup backup \
  --state /recovery/luxnix-state/gc-09 \
  --archive /recovery/credential-backups/gc-09-2026-11-06.tar.age \
  --identity /independent-encrypted-custody/credential-recovery.agekey
```

Backup encrypts an archive, decrypts and verifies every file and its recorded
ownership/mode in memory, rechecks live sources, then publishes ciphertext
atomically. Secret values and their hashes stay inside the encrypted archive.
The configurable size/file limits intentionally bound memory use; exceeding
them stops rather than silently skipping credentials. Stop credential rotation
and secret refresh while capturing/verifying. A missing source is never treated
as permission to invent a key or silently fall back to an older one.

## Verify after reboot and immediately before migration

```sh
devenv shell credential-backup verify \
  --state /recovery/luxnix-state/gc-09 \
  --archive /recovery/credential-backups/gc-09-2026-11-06.tar.age \
  --identity /independent-encrypted-custody/credential-recovery.agekey
```

This requires the original host and live source credentials. It compares the
plan/revision/lockfile, running system generation, configured paths, contents,
ownership, permissions, filesystem UUIDs and physical disk serials/sizes.
Legacy loop-container backing paths are included. Harmless `/dev/sdX` renumbering
is allowed; replacing a drive at the same mountpoint is not.

Any drift stops verification: **the old archive remains recoverable but is no
longer evidence for the current host state**. Review the change. Either revert
it deliberately and retest, or update the recovery procedure/test, create a new
reviewed plan when needed, and take a new backup. Never edit the manifest or
reuse an earlier approval. Verification is explicit, not a boot-time service;
run it after every reboot, credential rotation or configuration change and before
the destructive step. There is no automatic plan refresh or erasure approval.

## Restore testing and retirement

The age payload is a standard tar archive with `manifest.json` and
`files/<original-absolute-path-without-leading-slash>`. For an isolated restore
test, authenticate/decrypt with age and extract **only onto independent encrypted
storage**, preserving numeric ownership and modes. Do not extract over `/` or
publish a plaintext tar on the recovery drive. The manifest contains original
paths, content digests, ownership and modes for comparison. ACLs/extended
attributes and empty directory structure are not a full-system backup contract.

Use the restored copies to populate the custody layout required by
[secret preflight](boot-storage-migration.md); keep the original
controller Vault key in independent protected custody as required there. Test
that it decrypts the copied Vault and that the preserved password matches the
admin hash. Test client login after installation too. Backup authentication alone
does not prove Vault re-enrollment, restored login, application decryption or
recovery of database/media. Keep the existing preflight and operator assessments;
this command cannot substitute for them.
