# Luxnix Vault Overview and Bootstrap Guide

This page describes local vault storage and legacy encryption-key migration.
For the complete operator procedure, use the canonical
[Admin Password Creation and Rotation](admin-passwords.md) guide. It owns password
input creation, bootstrap/import, validation, export, installation and rotation.

## Vault building blocks

- **Vault directory (`~/.lxv/`)** – Stores encrypted secrets under
  `secrets/<secret_type>/<owner_type>/` and host-specific pre-shared keys in
  `psk/`.
- **Vault key (`~/.lxv.key`)** – Explicit master key for local ciphertext, labeled
  `luxnix-master`. Encryption and validation use this key directly, independent
  of Ansible configuration. A missing or incorrect key blocks an existing vault.
- **Pre-shared keys (PSKs)** – One file per inventory host. When present,
  secrets can be re-encrypted so they can be deployed to that host. The
  `Vault.get_or_create_psk()` helper maintains these files and wires them into
  `ansible.cfg` via the `vault_identity_list` setting.
- **Secret templates** – Blueprints that determine which secrets belong to
  roles, groups, local users, or hosts. Templates can either generate new
  secrets (using the password generator) or reference externally supplied
  values.
- **Secret entries** – Each secret stores metadata (owner, type, target name)
  plus an encrypted file on disk. They can be exported per host, generating
  deployable artefacts under `~/.lxv/deploy/<hostname>/`.
- **Ansible configuration** – `ansible.cfg` must reference the correct
  inventory, roles, libraries, private SSH key (`~/.ssh/id_ed25519`), and the
  PSK list so Ansible can transparently decrypt files.

All helper scripts ultimately use `lx_administration.models.vault.Vault`, which
handles inventory discovery, template generation, PSK creation, and secret
serialization.

## Legacy encryption-key migration

### Migrate legacy ciphertext before running the updated bootstrap

Older local vaults selected a hostname-labeled identity from ambient Ansible
configuration. Their key may be that control host's PSK rather than `.lxv.key`.
The updated tooling refuses those labels: it does not guess keys or rewrite old
ciphertext automatically. Keep the original encrypted store, metadata, PSKs and
keys together in the custodian backup before migration.

For each encrypted file, identify its old public header label and corresponding
private key file from the reviewed historical configuration. With operator
approval, create a separate encrypted copy through the cataloged helper:

```bash
devenv shell vault-migrate-local-key \
  --source <legacy-encrypted-file> --output <new-encrypted-file> \
  --legacy-key <actual-legacy-key-file> --legacy-id <old-label> \
  --master-key <private-master-key-file> --confirm-migration
```

For old Ansible 1.1 files without a label, use `--legacy-id default`. The helper
authenticates with exactly the supplied legacy key, writes only master-encrypted
bytes, verifies the new ciphertext and refuses an existing output. It never
replaces the original, removes keys or edits metadata. Stage a complete new vault
directory, update copied `vault.yml` secret/template paths to that directory,
and validate all secrets with `Vault.validate_local_key()` before switching to
it as a unit. Validate the admin mapping and create fresh host exports, then
perform a backup/restore exercise. Do not distribute a partially migrated vault
or delete old keys before recovery acceptance. This is a migration procedure,
not an emergency rollback to a compromised credential.

## Operator workflows

- [Admin password creation and rotation](admin-passwords.md): the canonical
  paired-password workflow, including first installation and failure recovery.
- [Hub machine enrollment](vault-hub-machine-enrollment.md): HashiCorp Vault
  AppRole, PKI and hub node-secret lifecycle.

For standalone secrets, `scripts/update_secret.py` updates local ciphertext and
metadata only. It refuses paired login credentials. Use `--prompt-value` for a
hidden custom-value prompt; never put a secret value in command arguments.
Export and consumer-specific adoption are separate operations. `sync-secrets`
copies files; it does not change live accounts, PostgreSQL roles or sessions.

Generated `conf/ansible.cfg` supplies inventory and registered PSK identities to
the supported wrappers. Keep its paths consistent with the selected vault.
Never inject plaintext admin mappings into ad-hoc Ansible extra variables.
