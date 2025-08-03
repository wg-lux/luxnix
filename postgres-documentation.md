# PostgreSQL Configuration Documentation for gc-10

## Overview

This document provides a comprehensive guide to the PostgreSQL configuration on the gc-10 host within the LuxNix infrastructure. The configuration supports the local endoreg-db-api service and follows LuxNix's modular architecture.

## Key Changes for Fully Declarative Setup

### PostgreSQL User and Password Management

The NixOS configuration now fully manages the `endoregDbLocal` user and its password through the `postgres-default` role:

1. **Automatic Password Generation**: If no password exists, the system generates one automatically
2. **Declarative User Creation**: The `endoregDbLocal` user is created with proper permissions
3. **Secure Password Storage**: Password is stored in `/etc/secrets/vault/SCRT_local_password_maintenance_password` with appropriate group permissions
4. **PostgreSQL Integration**: Password is automatically set in PostgreSQL during system activation

### Service Integration

The `endoreg-db-api-local` service is now fully integrated:

1. **Dependency Management**: Service waits for PostgreSQL setup to complete
2. **Password Access**: Service reads the centrally managed password
3. **No Manual Intervention**: Everything is handled declaratively by NixOS

### User and Group Management

- **System User**: `endoreg-service-user` is created declaratively by NixOS
- **Service Group**: `endoreg-service` group is enabled and configured
- **Permissions**: `endoreg-service-user` is added to the `sensitiveServices` group for secure file access

## Declarative Configuration Summary

The following NixOS modules work together to provide a fully declarative setup:

- `roles.postgres.default.enable = true;` - Creates PostgreSQL setup with `endoregDbLocal` user
- `roles.endoreg-client.enable = true;` - Enables the client role with user/group management
- `services.luxnix.endoregDbApiLocal.enable = true;` - Runs the service with proper dependencies

## Configuration Architecture

### Host Configuration (gc-10)

The gc-10 host is configured as a GPU client with the following key components:

- **Host Type**: GPU Client (`gc-10`)
- **VPN IP**: `172.16.255.110`
- **Role**: `endoreg-client` with local database API enabled
- **PostgreSQL**: Local instance for `endoregDbLocal` database

### Enabled Roles and Services

From `systems/x86_64-linux/gc-10/default.nix`:

```nix
roles = { 
  aglnet.client.enable = true;
  common.enable = true;
  custom-packages.cloud = true;
  custom-packages.enable = true;
  endoreg-client.dbApiLocal = true;        # Enables local DB API
  endoreg-client.enable = true;
  postgres.default.enable = true;          # Enables PostgreSQL
  # ... other roles
};
```

## PostgreSQL Service Configuration

### Service Stack

The PostgreSQL configuration involves three main modules:

1. **`services.luxnix.postgresql`** - Core PostgreSQL service
2. **`roles.postgres.default`** - Default PostgreSQL role configuration
3. **`services.luxnix.endoregDbApiLocal`** - Local endoreg API service

### Database Configuration

#### Default Databases

The following databases are automatically created:

```nix
ensureDatabases = [
  "admin"              # Admin user database
  "endoregDbLocal"     # Main application database
  "replication"        # Replication database
  "replUser"          # Replication user database
  "testUser"          # Test user database
  "devUser"           # Development user database
  "lxClientUser"      # LuxNix client user database
  "stagingUser"       # Staging user database
  "prodUser"          # Production user database
];
```

#### Default Users

The following PostgreSQL users are created with database ownership:

- `admin` - System administrator (with replication privileges)
- `endoregDbLocal` - Application database owner (with replication privileges)
- `replUser` - Replication user
- `testUser` - Test environment user
- `devUser` - Development user
- `lxClientUser` - LuxNix client user
- `stagingUser` - Staging environment user
- `prodUser` - Production user

### Authentication Configuration (pg_hba.conf)

The authentication rules are generated dynamically:

```bash
# Basic local authentication
local all                       postgres                                                trust
local all                       postgres                                                peer                map=superuser_map
local sameuser                  all                                                     peer                map=superuser_map

# Host-based authentication (IPv4)
host  all                       all                         127.0.0.1/32                scram-sha-256
host  replication               replUser                    127.0.0.1/32                scram-sha-256 
host  devUser                   devUser                     127.0.0.1/32                scram-sha-256
host  endoregDbLocal            endoregDbLocal              127.0.0.1/32                scram-sha-256

# IPv6 authentication (if required)
# Currently missing IPv6 rules for endoregDbLocal user
```

### Identity Mapping (pg_ident.conf)

```bash
# superuser_map mappings
superuser_map      root          postgres
superuser_map      root          replUser
superuser_map      admin         admin
superuser_map      admin         endoregClient
superuser_map      postgres      postgres
superuser_map      /^(.*)$       \1           # Generic mapping
```

## Current Connection Issue Analysis

### Error Details

The endoreg-db-api service is failing with these connection errors:

```
host: 'localhost', port: 5432, hostaddr: '::1': 
  FATAL: no pg_hba.conf entry for host "::1", user "endoregDbLocal", database "endoregDbLocal", no encryption

host: 'localhost', port: 5432, hostaddr: '127.0.0.1': 
  FATAL: password authentication failed for user "endoregDbLocal"
```

### Root Cause Analysis

1. **IPv6 Connection Issue**: Missing pg_hba.conf entry for IPv6 localhost (`::1`)
2. **Password Authentication**: The `endoregDbLocal` user needs a password set
3. **Connection Preference**: The application tries IPv6 first, then IPv4

### Database Status

Based on the provided database list:

```sql
-- Databases exist correctly
endoregDbLocal | endoregDbLocal | UTF8 | libc | en_US.UTF-8 | en_US.UTF-8
```

## Password Management

### Current Password Setup

The endoreg-db-api service manages passwords through:

```bash
# Password file location
${repoDir}/conf/db_pwd

# Vault password source
~/secrets/vault/SCRT_local_password_maintenance_password
```

### Password Generation Logic

From the service configuration:

```bash
if [ ! -f ${repoDir}/conf/db_pwd ]; then
  if [ -f ~/secrets/vault/SCRT_local_password_maintenance_password ]; then
    cp ~/secrets/vault/SCRT_local_password_maintenance_password ${repoDir}/conf/db_pwd
  else
    mkdir -p ~/secrets/vault
    openssl rand -base64 32 > ~/secrets/vault/SCRT_local_password_maintenance_password
    cp ~/secrets/vault/SCRT_local_password_maintenance_password ${repoDir}/conf/db_pwd
  fi
fi
```

## Troubleshooting Steps

### 1. Check PostgreSQL Status

```bash
# On gc-10 via SSH
systemctl status postgresql
sudo -u postgres psql -c "\du"  # List users
sudo -u postgres psql -c "\l"   # List databases
```

### 2. Verify pg_hba.conf Configuration

```bash
# View current pg_hba.conf
sudo cat /var/lib/postgresql/16/pg_hba.conf

# Check for IPv6 entry for endoregDbLocal
grep -n "::1" /var/lib/postgresql/16/pg_hba.conf
```

### 3. Set Password for endoregDbLocal User

```bash
# Connect as postgres superuser
sudo -u postgres psql

# Set password for endoregDbLocal user (using safe dollar-quoting)
ALTER USER "endoregDbLocal" WITH PASSWORD $securepass$your_password_here$securepass$;

# Alternative: Use \password command for interactive password setting
\password endoregDbLocal

# Verify user exists and has correct privileges
\du endoregDbLocal
```

### 4. Check Service User Home Directory

```bash
# Check endoreg-service-user home and permissions
ls -la /var/endoreg-service-user/
ls -la /var/endoreg-service-user/endo-api/conf/
```

## Configuration Fixes

### Fix 1: Add IPv6 Authentication Rule

The pg_hba.conf needs an IPv6 entry for the `endoregDbLocal` user. This should be added to the PostgreSQL service configuration.

### Fix 2: Ensure Password Synchronization

The password in the vault file must match the PostgreSQL user password.

### Fix 3: Service Dependencies

Ensure the endoreg-db-api service starts after PostgreSQL is fully ready.

## Service Architecture

### Service Dependencies

```
endoreg-client.enable = true
├── endoreg-client.dbApiLocal = true
│   ├── services.luxnix.endoregDbApiLocal.enable = true
│   │   └── systemd.services."endo-api-boot"
│   └── luxnix.generic-settings.postgres.enable = true
└── postgres.default.enable = true
    └── services.luxnix.postgresql.enable = true
        └── services.postgresql (NixOS native)
```

### User Management

- **System User**: `endoreg-service-user` (service account)
- **PostgreSQL User**: `endoregDbLocal` (database owner)
- **Admin User**: `admin` (system administrator)

## Network Configuration

### Local Connections

- **PostgreSQL Port**: 5432
- **Listen Addresses**: `localhost,127.0.0.1`
- **Local Socket**: `/run/postgresql`

### VPN Network

- **gc-10 VPN IP**: `172.16.255.110`
- **Admin VPN IP**: `172.16.255.106`
- **VPN Subnet**: `172.16.255.0/24`

## Monitoring and Logs

### Service Logs

```bash
# endoreg-db-api service logs
journalctl -u endo-api-boot -f

# PostgreSQL logs
journalctl -u postgresql -f

# System logs for postgres
sudo tail -f /var/log/postgresql/postgresql-16-main.log
```

### Configuration Validation

```bash
# Validate PostgreSQL configuration
sudo -u postgres postgres --check

# Test connection as different users
sudo -u postgres psql -d endoregDbLocal -U postgres
```

## Security Considerations

### Authentication Methods

- **Local connections**: `trust` and `peer` with identity mapping
- **Host connections**: `scram-sha-256` (secure password authentication)
- **Remote admin**: Requires VPN access from admin IP

### File Permissions

- **Database directory**: `/var/lib/postgresql/16` (postgres:postgres)
- **Service user home**: `/var/endoreg-service-user` (endoreg-service-user:users)
- **Secrets directory**: `/etc/secrets/vault` (admin:sensitiveServices)

## Maintenance Commands

### Database Maintenance

```bash
# Show PostgreSQL configuration
show-psql-conf

# Reset PostgreSQL data (safe with confirmation)
reset-psql-safe

# For Nextcloud hosts, use the maintenance script
nextcloud-maintenance --reset-psql

# Manual backup
sudo -u postgres pg_dump endoregDbLocal > backup.sql
```

### Service Management

```bash
# Restart endoreg-db-api service
systemctl restart endo-api-boot

# Restart PostgreSQL
systemctl restart postgresql

# Rebuild NixOS configuration
nh os switch
```

## Future Improvements

1. **IPv6 Support**: Add proper IPv6 authentication rules
2. **Password Management**: Integrate with LuxNix vault system
3. **Monitoring**: Add PostgreSQL monitoring and alerting
4. **Backup Strategy**: Implement automated backups to remote storage
5. **Connection Pooling**: Consider pgbouncer for connection management

## Related Documentation

- [LuxNix Generic Settings](modules/nixos/luxnix/generic-settings/default.nix)
- [PostgreSQL Service](modules/nixos/services/postgres/default.nix)
- [Endoreg Client Role](modules/nixos/roles/endoreg-client/default.nix)
- [Security Documentation](docs/security.md)

## Quick Fix Guide

### Immediate Steps to Resolve Connection Issues

1. **Run the debug script** to assess the current state:
   ```bash
   ./scripts/debug-postgres-gc10.sh
   ```

2. **Apply the automated fix**:
   ```bash
   ./scripts/fix-postgres-gc10.sh
   ```

3. **Update the NixOS configuration** to include IPv6 support:
   ```bash
   # On gc-10 (via SSH)
   cd /home/admin/luxnix
   nh os switch
   ```

4. **Verify the fix**:
   ```bash
   # Check service status
   systemctl status endo-api-boot
   
   # Check recent logs
   journalctl -u endo-api-boot --since '5 minutes ago'
   ```

### Manual Verification Steps

Connect to gc-10 via SSH and run these commands:

```bash
# Check PostgreSQL is running
systemctl status postgresql

# Verify databases and users exist
sudo -u postgres psql -c "\l"
sudo -u postgres psql -c "\du"

# Test database connection
PGPASSWORD="$(cat /home/admin/secrets/vault/SCRT_local_password_maintenance_password)" \
  psql -h 127.0.0.1 -d endoregDbLocal -U endoregDbLocal -c "SELECT version();"

# Check pg_hba.conf includes IPv6 entry
sudo grep -A5 -B5 "::1" /var/lib/postgresql/16/pg_hba.conf

# Verify service user can access password file
sudo -u endoreg-service-user cat /var/endoreg-service-user/endo-api/conf/db_pwd
```

### Configuration Changes Made

1. **Added IPv6 authentication rule** in `modules/nixos/services/postgres/default.nix`:
   ```nix
   + (if defaults.enable then "\nhost ${defaults.defaultDbName} ${defaults.defaultDbName} ::1/128 scram-sha-256" else "")
   ```

2. **Password synchronization** between vault and service user locations

3. **Proper file permissions** for database password files

### Service Flow Verification

The complete service startup flow should work as follows:

1. **PostgreSQL starts** and creates users/databases
2. **Password is synchronized** from vault to service location
3. **endoreg-db-api service starts** and can connect to database
4. **Application runs successfully** with database connectivity

### Configuration Analysis and Fixes

After analyzing the NixOS configuration, I identified the root issues with the PostgreSQL connection for the `endoreg-service-user`:

### Current Configuration Flow

1. **User Creation**: `modules/nixos/user/endoreg-service-user/default.nix`
   - Creates system user `endoreg-service-user` (UID: 400)
   - Creates group `endoreg-service` (GID: 101) 
   - Home directory: `/var/endoreg-service-user`

2. **Service Configuration**: `modules/nixos/services/endoreg-db-api-local/default.nix`
   - Service runs as `endoreg-service-user`
   - Tries to connect to database `endoregDbLocal` as user `endoregDbLocal`
   - Password management is handled in the service script

3. **PostgreSQL Configuration**: `modules/nixos/services/postgres/default.nix`
   - Creates PostgreSQL user `endoregDbLocal` (from `roles.postgres.default.defaultDbName`)
   - Authentication rules exist but IPv6 support was missing (now fixed)

### Issues Identified

1. **Missing Group Creation**: The `endoreg-service` group is defined in `group/service/default.nix` but not automatically enabled
2. **Password Synchronization**: The service script manages passwords manually, but PostgreSQL user password may not be set
3. **Authentication Flow**: The service user (`endoreg-service-user`) connects as DB user (`endoregDbLocal`) but this mapping isn't clearly defined
4. **IPv6 Support**: Missing IPv6 authentication rules (already fixed above)

### Required Configuration Changes

#### 1. Ensure Group Creation

The `endoreg-service` group needs to be created. Add this to the endoreg-client role:

```nix
# In roles/endoreg-client/default.nix
users.groups.endoreg-service = {
  gid = 101;
  members = [ "endoreg-service-user" ];
};
```

#### 2. Password Management

Ensure the password for `endoregDbLocal` is set and matches the service password file.

#### 3. Authentication Mapping

Clarify the authentication mapping between `endoreg-service-user` and `endoregDbLocal`.

## Additional Considerations

- Review and apply the configuration changes.
- Monitor the system after applying changes to ensure stability.
- Plan for a maintenance window if disruptive changes are made.

## Verification Commands

After deploying the new configuration, verify the setup works correctly:

### 1. Check PostgreSQL User Exists
```bash
sudo -u postgres psql -c "\du" | grep endoregDbLocal
```

### 2. Check Database Exists
```bash
sudo -u postgres psql -c "\l" | grep endoregDbLocal
```

### 3. Test Password Authentication
```bash
PGPASSWORD="$(sudo cat /etc/secrets/vault/SCRT_local_password_maintenance_password)" \
psql -h localhost -U endoregDbLocal -d endoregDbLocal -c "SELECT current_user;"
```

### 4. Check Service Status
```bash
systemctl status endo-api-boot
systemctl status postgres-endoreg-setup
```

### 5. Verify User and Group Creation
```bash
id endoreg-service-user
getent group endoreg-service
```

## Deployment Instructions

To deploy the new configuration to gc-10:

1. **Rebuild the configuration**:
   ```bash
   sudo nixos-rebuild switch
   ```

2. **Verify services are running**:
   ```bash
   systemctl status postgresql
   systemctl status postgres-endoreg-setup
   systemctl status endo-api-boot
   ```

3. **Check logs if needed**:
   ```bash
   journalctl -u postgres-endoreg-setup
   journalctl -u endo-api-boot
   ```

## Troubleshooting the New Setup

If issues occur with the new declarative setup:

### Service Won't Start
1. Check if PostgreSQL is running: `systemctl status postgresql`
2. Check password setup service: `journalctl -u postgres-endoreg-setup`
3. Verify password file exists: `ls -la /etc/secrets/vault/SCRT_local_password_maintenance_password`

### Authentication Failures
1. Check pg_hba.conf includes the endoregDbLocal user authentication
2. Verify password is set correctly in PostgreSQL
3. Test direct connection as shown in verification commands above

### Service User Issues
1. Verify user exists: `id endoreg-service-user`
2. Check group membership: `groups endoreg-service-user`
3. Verify file permissions: `ls -la /etc/secrets/vault/`