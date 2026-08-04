# Managed Secrets Role

The `managed-secrets` role automatically generates and manages commonly used secret files in the LuxNix system. This role is enabled by default in the `common` role to ensure that all required secrets are available on freshly deployed machines.

## Features

- **Automatic Generation**: Creates missing secret files on system boot
- **Atomic Writes**: Refreshes secrets through same-directory temp files and atomic replacement
- **Proper Permissions**: Sets correct ownership and permissions (root:sensitive-service-group 640)
- **Refresh Support**: Can refresh selected secrets on every run
- **Vault-Aware Runtime Integration**: Can consume Vault credentials from a dedicated systemd runtime environment
- **Management Tools**: Provides CLI tools for secret management

## Important Semantics

`managed-secrets` now supports three behaviors:

- create-if-missing
- force regeneration
- refresh-on-boot

That means:

- if a target file does not exist, it is generated or materialized
- if `refreshOnBoot = true`, the file is regenerated or re-fetched on every service run
- if `forceRegenerate = true`, the file is also regenerated even if it already exists

This is especially important for externally sourced secrets, including Vault-backed custom secrets.

`customSecrets` now participate in the same generation loop as the built-in secrets. They get the same create-if-missing, refresh, force-regenerate, permission, and atomic-write handling.

## Human-Facing Password Policy

`managed-secrets` is only for machine-generated service secrets by default. It
does not generate passwords that people must know or type interactively.

These built-ins are disabled by default and should be supplied by SOPS or an
existing hash file instead:

- `client_user_password`
- `client_user_password_hash`
- `nextcloud_admin_password`

If a SOPS secret writes to the same deployed `path` as a managed secret,
evaluation fails until the corresponding `roles.managed-secrets` entry is
disabled. This prevents two secret systems from racing over the same file.

Custom secrets can opt into the same guard with `humanFacing = true`.

For a short migration only, generated human-facing built-ins can be enabled
with:

```nix
roles.managed-secrets.allowGeneratedHumanSecrets = true;
```

Do not leave that enabled for steady-state deployments.

## Managed Secrets

The following secrets are automatically managed:

### Database Secrets
- **`/etc/secrets/vault/SCRT_local_password_maintenance_password`**: PostgreSQL maintenance user password
  - Used by: postgres-default role, endoreg-client role

### Django Application Secrets  
- **`/etc/secrets/vault/django_secret_key`**: Django SECRET_KEY for local API instances
- **`/etc/secrets/vault/django_central_secret_key`**: Django SECRET_KEY for central API instances
  - Used by: lx-annotate through the endoreg-client role

### Nextcloud Secrets
- **`/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_minio_credentials`**: MinIO credentials for Nextcloud
  - Used by: nextcloud-host role

The Nextcloud admin password path is still available as the
`nextcloud_admin_password` built-in, but it is human-facing and therefore
disabled by default. Prefer a SOPS secret that writes to
`/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_password`.

## Configuration

### Basic Usage
The role is enabled by default. To disable it:

```nix
roles.managed-secrets.enable = false;
```

### Individual Secret Control
You can disable specific secrets:

```nix
roles.managed-secrets.secrets.django_secret_key.enable = false;
```

When SOPS owns the same target path, disable the generated secret:

```nix
roles.managed-secrets.secrets.nextcloud_admin_password.enable = false;

sops.secrets."nextcloud-admin-password" = {
  sopsFile = ./secrets.yaml;
  path = "/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_password";
  owner = "root";
  group = config.luxnix.generic-settings.sensitiveServiceGroupName;
  mode = "0640";
};
```

### Custom Secrets
Add your own managed secrets:

```nix
roles.managed-secrets.customSecrets.my-app-key = {
  path = "/etc/secrets/vault/my_app_secret";
  generator = "openssl rand -hex 32";
  description = "My application secret key";
  refreshOnBoot = true;
};
```

For Vault-backed custom secrets, the common pattern is:

```nix
roles.managed-secrets.customSecrets.my-vault-secret = {
  path = "/etc/secrets/vault/my_vault_secret";
  owner = "root";
  group = "root";
  permissions = "0400";
  refreshOnBoot = true;
  generator = ''
    ${pkgs.vault}/bin/vault kv get -field=my_field secret/data/nodes/${config.networking.hostName}/my-app
  '';
};
```

If the host uses `luxnix.vault.client`, `managed-secrets-setup.service` can consume the runtime Vault environment prepared by `vault-auth-setup.service`, so Vault-backed generators do not depend on root's interactive shell environment.

## Management Commands

### CLI Tool: `luxnix-secrets`

```bash
# Check status of all secrets
luxnix-secrets check
# or: secrets-check

# Generate missing secrets
luxnix-secrets generate  
# or: secrets-generate

# List all managed secrets
luxnix-secrets list
# or: secrets-list

# Force regenerate all secrets (dangerous!)
luxnix-secrets regenerate
```

### SystemD Service

```bash
# Manual trigger secret generation
sudo systemctl start managed-secrets-setup.service

# Check service status
sudo systemctl status managed-secrets-setup.service
```

If Vault-backed generation is enabled on the host, also inspect:

```bash
sudo systemctl status vault-auth-setup.service
```

## Security

- All secrets are generated using cryptographically secure methods (`openssl rand`)
- Refreshed secrets are written atomically to reduce partial-write risk
- Files are created with restrictive permissions (640)
- Owner: `root`, Group: `sensitive-service-group`
- Directory structure uses proper permissions (700 for `/etc/secrets`, 750 for `/etc/secrets/vault`)

## Dependencies

- Runs early in boot process before services that need secrets
- Other services depend on `managed-secrets-setup.service`
- Requires `sensitive-service-group` to exist (created by generic-settings)
- When `luxnix.vault.client` is enabled, `managed-secrets-setup.service` can be ordered after `vault-auth-setup.service` and consume `/run/luxnix/vault/vault.env`

## Troubleshooting

### Missing Secrets on Fresh Deployment
If secrets are missing on a new machine:

```bash
# Check if the service ran
sudo systemctl status managed-secrets-setup.service

# Manual generation
sudo systemctl start managed-secrets-setup.service

# Verify secrets exist
secrets-check
```

### Permission Issues
If services can't read secrets:

```bash
# Check file permissions
ls -la /etc/secrets/vault/

# Fix permissions (service should handle this automatically)
sudo systemctl restart managed-secrets-setup.service
```

### Service Dependency Issues
If services fail because secrets aren't ready:

```bash
# Check service order
systemctl list-dependencies managed-secrets-setup.service

# Restart dependent services
sudo systemctl restart postgres-endoreg-setup.service
sudo systemctl restart lx-annotate-runtime-env.service
sudo systemctl restart lx-annotate-feature-registry-guard.service
sudo systemctl restart lx-annotate.service
```

If the failing secret is Vault-backed, inspect the chain in order:

```bash
sudo systemctl status vault-auth-setup.service
sudo systemctl status managed-secrets-setup.service
sudo journalctl -u vault-auth-setup.service -b
sudo journalctl -u managed-secrets-setup.service -b
```

If the failing secret is Vault-backed, inspect the chain in order:

```bash
sudo systemctl status vault-auth-setup.service
sudo systemctl status managed-secrets-setup.service
sudo journalctl -u vault-auth-setup.service -b
sudo journalctl -u managed-secrets-setup.service -b
```

## Integration

Services that depend on managed secrets should:

1. Add dependency in systemd service:
   ```nix
   after = [ "managed-secrets-setup.service" ];
   requires = [ "managed-secrets-setup.service" ];
   ```

2. Reference secret files using the standard paths:
   ```nix
   passwordFile = "/etc/secrets/vault/SCRT_local_password_maintenance_password";
   ```

The managed-secrets role ensures these files exist before dependent services start.

## Related Docs

- [lx-annotate Encrypted Data](/home/admin/luxnix/docs/lx-annotate-encrypted-data.md)
- [Nixtest Safety Suite](/home/admin/luxnix/docs/testing-nixtests.md)
