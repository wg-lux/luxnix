# Managed Secrets Role

The `managed-secrets` role automatically generates and manages commonly used secret files in the LuxNix system. This role is enabled by default in the `common` role to ensure that all required secrets are available on freshly deployed machines.

## Features

- **Automatic Generation**: Creates missing secret files on system boot
- **Proper Permissions**: Sets correct ownership and permissions (root:sensitive-service-group 640)
- **Idempotent**: Only generates secrets that don't already exist
- **Management Tools**: Provides CLI tools for secret management

## Managed Secrets

The following secrets are automatically managed:

### Database Secrets
- **`/etc/secrets/vault/SCRT_local_password_maintenance_password`**: PostgreSQL maintenance user password
  - Used by: postgres-default role, endoreg-client role

### Django Application Secrets  
- **`/etc/secrets/vault/django_secret_key`**: Django SECRET_KEY for local API instances
- **`/etc/secrets/vault/django_central_secret_key`**: Django SECRET_KEY for central API instances
  - Used by: endoreg-client role, endoreg-db-central-01 role

### Nextcloud Secrets
- **`/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_password`**: Nextcloud admin password
- **`/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_minio_credentials`**: MinIO credentials for Nextcloud
  - Used by: nextcloud-host role

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

### Custom Secrets
Add your own managed secrets:

```nix
roles.managed-secrets.customSecrets.my-app-key = {
  path = "/etc/secrets/vault/my_app_secret";
  generator = "openssl rand -hex 32";
  description = "My application secret key";
};
```

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

## Security

- All secrets are generated using cryptographically secure methods (`openssl rand`)
- Files are created with restrictive permissions (640)
- Owner: `root`, Group: `sensitive-service-group`
- Directory structure uses proper permissions (700 for `/etc/secrets`, 750 for `/etc/secrets/vault`)

## Dependencies

- Runs early in boot process before services that need secrets
- Other services depend on `managed-secrets-setup.service`
- Requires `sensitive-service-group` to exist (created by generic-settings)

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
sudo systemctl restart endo-api-boot.service
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
