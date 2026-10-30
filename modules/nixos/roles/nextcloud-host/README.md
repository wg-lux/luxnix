# Nextcloud Host Role

This role configures a complete Nextcloud installation with PostgreSQL database and Garage object storage.

## Services Configured

- Nextcloud server
- PostgreSQL database
- Garage object storage
- Nginx reverse proxy
- Whiteboard server

## Version and upgrades

The role default and canonical Ansible role input select `pkgs.nextcloud33`
(33.0.10 in the current flake lock), replacing the end-of-life Nextcloud 32
selection. The generated `s-03` configuration uses the same package. No
insecure-package exception or flake input update is required.

Before activating this change on `s-03`, verify the installed version using
`nextcloud-occ status`. The repository's previous selection was 32.0.15;
that does not establish the version currently installed on the host.
Nextcloud requires the latest maintenance release of the current major before
advancing one major at a time. If the running version is older than 32, complete
the intermediate upgrades first. See the
[official upgrade requirements](https://docs.nextcloud.com/server/stable/admin_manual/maintenance/upgrade.html).

Back up PostgreSQL, the Garage object store and Nextcloud configuration, and
check installed third-party app compatibility before activation. The NixOS
`nextcloud-setup` service runs the application upgrade; do not use the destructive
reset commands below for an upgrade. Allow background migrations to finish and
check service health and file access afterward. Reverting a Nix generation does
not undo a database migration; recovery requires the matching data backup.

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

# Reset Garage data (with interactive confirmation)
nextcloud-maintenance --reset-garage

# Reset all Nextcloud data (with interactive confirmation)
nextcloud-maintenance --reset-all
```

### Shell Aliases

The following safe aliases are available:

- `show-psql-conf` - Display PostgreSQL configuration
- `nextcloud-maintenance` - Run the maintenance script
- `reset-psql-safe` - Interactive PostgreSQL reset
- `reset-garage-safe` - Interactive Garage reset
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
   sudo systemctl stop nginx.service postgresql.service garage.service
   ```

2. **For PostgreSQL reset:**
   ```bash
   # Remove PostgreSQL data (replace VERSION with actual version)
   sudo rm -rf /var/lib/postgresql/VERSION
   ```

3. **For Garage reset:**
   ```bash
   # Remove Garage data
   sudo rm -rf /var/lib/garage
   ```

4. **After reset operations:**
   ```bash
   # Reinitialize services
   nixos-rebuild switch
   ```

### Backup Recommendations

Before performing any reset operations, ensure you have backups:

- **Database backup**: Use `pg_dump` to backup PostgreSQL data
- **File storage backup**: Backup Garage data directory
- **Nextcloud config**: Backup Nextcloud configuration files

### Migration from Old Aliases

If you were previously using the dangerous `reset-psql` or `reset-garage` aliases:

- Replace `reset-psql` with `reset-psql-safe`
- Replace `reset-garage` with `reset-garage-safe`
- Use `nextcloud-maintenance --help` to see all available options

The new commands provide the same functionality but with proper safety checks and confirmations.
