# PostgreSQL Security Improvements

## SQL Injection Prevention

### Fixed: Password Interpolation Vulnerability

**Issue**: The original code directly interpolated passwords into SQL commands:
```bash
psql -c "ALTER USER \"user\" WITH PASSWORD '$PASSWORD';"
```

This created a SQL injection risk if passwords contained special characters like single quotes, semicolons, or backslashes.

**Solution**: Implemented safe password handling using PostgreSQL's dollar-quoting feature:
```bash
psql -c "ALTER USER \"user\" WITH PASSWORD \$securepass\$${PASSWORD}\$securepass\$;"
```

### Why Dollar-Quoting is Safe

Dollar-quoting (`$tag$content$tag$`) treats the enclosed content as a literal string, preventing interpretation of special characters:

- **Safe against**: Single quotes, double quotes, backslashes, semicolons
- **No escaping needed**: Content between dollar-quote tags is treated literally
- **PostgreSQL standard**: Recommended approach for handling arbitrary strings

### Alternative Safe Methods

1. **Interactive password setting** (most secure):
   ```bash
   psql -c "\password username"
   ```

2. **Environment variable** (avoids command line exposure):
   ```bash
   PGPASSWORD="$password" psql -c "..."
   ```

3. **Prepared statements** (for application code):
   ```sql
   PREPARE stmt AS 'ALTER USER $1 WITH PASSWORD $2';
   EXECUTE stmt('username', 'password');
   ```

### Files Updated

- `modules/nixos/roles/postgres-default/default.nix`: Fixed password interpolation and directory permissions
- `postgres-documentation.md`: Updated examples to show safe practices

This change ensures that passwords with special characters (e.g., `p@$$w0rd';"DROP TABLE;`) are handled safely without risk of SQL injection.

## Directory Permission Hardening

### Fixed: Overpermissive Secret Directory Permissions

**Issue**: Secret directories were created with overly permissive 0755 permissions:
```nix
systemd.tmpfiles.rules = [
  "d /etc/secrets 0755 root root -"
  "d /etc/secrets/vault 0755 root root -"
];
```

This allowed any user on the system to read the directory contents and potentially access sensitive files.

**Solution**: Restricted permissions to 0700 (owner-only access):
```nix
systemd.tmpfiles.rules = [
  "d /etc/secrets 0700 root root -"
  "d /etc/secrets/vault 0700 root root -"
];
```

### Security Benefits

- **Principle of least privilege**: Only root can access secret directories
- **Defense in depth**: Even if file permissions are misconfigured, directory access is restricted  
- **Prevents information disclosure**: Other users cannot list or traverse secret directories
- **Compliance**: Follows security best practices for sensitive data storage

### Permission Levels Explained

- **0755**: Read/write/execute for owner, read/execute for group and others (too permissive)
- **0700**: Read/write/execute for owner only (recommended for secrets)
- **0750**: Read/write/execute for owner, read/execute for group (appropriate for service-specific secrets)

### Files Updated

- `modules/nixos/roles/postgres-default/default.nix`: Hardened secret directory permissions
- `modules/nixos/luxnix/generic-settings/default.nix`: Hardened secret directory permissions
