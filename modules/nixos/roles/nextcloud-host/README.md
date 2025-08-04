# Nextcloud Host Role

This role configures a complete Nextcloud installation with PostgreSQL database and MinIO object storage.

## Services Configured

- Nextcloud server
- PostgreSQL database
- MinIO object storage
- Nginx reverse proxy
- Whiteboard server

## Maintenance Operations

### Safe Reset Commands

The role provides safe maintenance commands through the `nextcloud-maintenance` script that includes proper confirmations and service management:

```bash
# Show available maintenance options
nextcloud-maintenance

# Show PostgreSQL configuration
nextcloud-maintenance --show-psql-conf

# Reset PostgreSQL data (with interactive confirmation)
nextcloud-maintenance --reset-psql

# Reset MinIO data (with interactive confirmation)  
nextcloud-maintenance --reset-minio

# Reset all Nextcloud data (with interactive confirmation)
nextcloud-maintenance --reset-all
```

### Shell Aliases

The following safe aliases are available:

- `show-psql-conf` - Display PostgreSQL configuration
- `nextcloud-maintenance` - Run the maintenance script
- `reset-psql-safe` - Interactive PostgreSQL reset
- `reset-minio-safe` - Interactive MinIO reset  
- `reset-nextcloud-all` - Interactive reset of all services

### Safety Features

The maintenance script includes:

- **Interactive confirmation**: All destructive operations require typing 'yes' to proceed
- **Service management**: Automatically stops relevant services before operations
- **Path verification**: Checks that target directories exist before attempting deletion
- **Clear warnings**: Displays what will be deleted and warns about data loss
- **Operation logging**: Shows progress and completion status

### Manual Recovery Steps

If you need to perform maintenance operations manually:

1. **Before any reset operation:**
   ```bash
   # Stop all related services
   sudo systemctl stop nextcloud-setup.service nextcloud-cron.service
   sudo systemctl stop nginx.service postgresql.service minio.service
   ```

2. **For PostgreSQL reset:**
   ```bash
   # Remove PostgreSQL data (replace VERSION with actual version)
   sudo rm -rf /var/lib/postgresql/VERSION
   ```

3. **For MinIO reset:**
   ```bash
   # Remove MinIO data
   sudo rm -rf /var/lib/minio
   ```

4. **After reset operations:**
   ```bash
   # Reinitialize services
   nixos-rebuild switch
   ```

### Backup Recommendations

Before performing any reset operations, ensure you have backups:

- **Database backup**: Use `pg_dump` to backup PostgreSQL data
- **File storage backup**: Backup MinIO data directory
- **Nextcloud config**: Backup Nextcloud configuration files

### Migration from Old Aliases

If you were previously using the dangerous `reset-psql` or `reset-minio` aliases:

- Replace `reset-psql` with `reset-psql-safe`
- Replace `reset-minio` with `reset-minio-safe`
- Use `nextcloud-maintenance --help` to see all available options

The new commands provide the same functionality but with proper safety checks and confirmations.
