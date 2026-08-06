# Luxnix Vault Overview and Bootstrap Guide

This guide explains how the Luxnix vault tooling works and how to initialise a
fresh password store on a new control host.

## Vault building blocks

- **Vault directory (`~/.lxv/`)** – Stores encrypted secrets under
  `secrets/<secret_type>/<owner_type>/` and host-specific pre-shared keys in
  `psk/`.
- **Vault key (`~/.lxv.key`)** – Local passphrase used with Ansible Vault to
  encrypt newly created or rotated secrets.
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

## Bootstrap prerequisites

1. Ensure password-less SSH access from the current control host to each
   managed node using `~/.ssh/id_ed25519`.
2. Collect the admin user passwords for every host defined in
   `systems/<arch>/*/default.nix`. Use
   `ansible/admin-passwords.example.yml` as a template and save the
   populated file as `ansible/secrets/admin-passwords.yml` (keep it
   untracked).
3. Verify that `ansible/inventory/hosts.ini` is up to date – the bootstrap
   process uses it (via the generated `autoconf/inventory.yml`) to decide which
   secrets to create.

## Bootstrapping a fresh vault

Run the helper script from the repository root through the declared development
environment:

```bash
devenv shell vault-bootstrap \
  --vault-dir ~/.lxv \
  --vault-key ~/.lxv.key \
  --local-hostname <control-host> \
  --admin-passwords <admin-passwords-file> \
  --export
```

Outside of the dev shell you can call the script directly:

```bash
python scripts/bootstrap-lx-vault.py \
  --vault-dir ~/.lxv \
  --vault-key ~/.lxv.key \
  --local-hostname <control-host> \
  --admin-passwords <admin-passwords-file> \
  --export
```

The inventory defaults to the generated path declared by
`autoconf/config.yml`. Use `--inventory <path>` for a one-off override or
`--autoconf-config <path>` when the complete Autoconf layout differs.

What the script does:

1. Creates `~/.lxv/` (if missing) and generates `~/.lxv.key` with a secure
   passphrase.
2. Copies `conf/TEMPLATE_ansible.cfg` to `conf/ansible.cfg`, updates the log
   location to `./logs/ansible.log`, and pins the SSH private key to
   `~/.ssh/id_ed25519`.
3. Loads or creates `~/.lxv/vault.yml`.
4. Syncs the inventory to generate/update secret templates and PSKs. Each PSK
   entry is wired into `ansible.cfg` automatically.
5. Imports the provided admin passwords, storing both the plaintext and hashed
   versions in the vault under predictable target names such as
   `SCRT_local_password_admin_password`.
6. Optionally (`--export`) re-encrypts secrets per host into
   `~/.lxv/deploy/<hostname>/` for distribution.

### Re-running the bootstrap

The script is idempotent:

- Existing PSKs are reused and `ansible.cfg` is kept in sync.
- Admin passwords are rotated in place—both plaintext and hash secrets are
  re-encrypted.
- Use `--skip-sync` if you only need to import new passwords without touching
  templates or PSKs.

## Using the vault in Ansible runs

- The generated `conf/ansible.cfg` is referenced automatically by helper
  scripts such as `scripts/check-connectivity.sh`.
- To inject the admin password mapping during ad-hoc runs, pass
  `--extra-vars @ansible/secrets/admin-passwords.yml` to `ansible-playbook`.
- Logs are written to `./logs/ansible.log`; make sure the `logs/` directory
  exists (`git` ignores it, so create it locally if needed).

Common helper wrappers available via `devenv shell`:

- `devenv shell vault-bootstrap …` – run the bootstrapper with custom flags.
- `devenv shell validate-admin-passwords …` – verify that the vault matches
  the source password file.
- `devenv shell check-connectivity <target>` – execute the connectivity check
  playbook and write the log into `./logs/`.

For local setup using the bootstrap script's default paths and no extra
arguments, automation can invoke the underlying cataloged task:

```bash
devenv tasks run autoconf:initialize-vault
```

Use `devenv shell vault-bootstrap …` when supplying an admin-password file,
overriding paths, selecting the control hostname, or exporting host bundles.

## Rotating secrets or adding new hosts

1. Update `ansible/inventory/hosts.ini` and regenerate `autoconf/inventory.yml`
   if new hosts or roles are introduced.
2. Re-run `bootstrap-lx-vault.py` to create PSKs and baseline secrets for the
   new entries.
3. Use `scripts/update_secret.py` for ad-hoc secret rotation. The helper uses
   the same vault metadata and encrypts updates with the local key.

   For example, rotate one generated password without exposing its value in
   the command line:

   ```bash
   python scripts/update_secret.py \
     --vault-dir ~/.lxv \
     --vault-key ~/.lxv.key \
     --secret-name <secret-name> \
     --mode password \
     --key-length 20
   ```

With these steps you can rebuild the Luxnix vault on a fresh workstation,
import existing admin credentials, and keep Ansible configured to use the
trusted control-host SSH identity.

## Validating stored admin passwords

After bootstrapping (or whenever passwords change) you can validate that the
vault contents match the source file:

```bash
devenv shell validate-admin-passwords \
  --vault-dir ~/.lxv \
  --vault-key ~/.lxv.key \
  --admin-passwords ansible/secrets/admin-passwords.yml \
  --vault-id <control-hostname>
```

The command verifies both the plaintext password and the stored hash for every
hostname in the YAML file. A non-zero exit code indicates missing secrets or a
mismatch.
