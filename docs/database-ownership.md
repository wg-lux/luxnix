# Database Ownership and Legacy Names

This page documents the current ownership of the local PostgreSQL database used by `lx-annotate-local`, and explains the legacy names that can otherwise be misleading.

## Current Model

For normal EndoReg client hosts, `lx-annotate-local` uses the database configuration from `roles.endoreg-client.database`.

The default database settings are:

```nix
roles.endoreg-client.database = {
  host = "localhost";
  port = 5432;
  name = "endoregDbLocal";
  user = "endoregDbLocal";
  passwordFile = "/etc/secrets/vault/SCRT_local_password_maintenance_password";
  endoregLocalUserPasswordFile = "/var/lib/postgresql/endoregDbLocal.password";
  sslMode = "prefer";
};
```

The wiring is in `modules/nixos/roles/endoreg-client/default.nix`:

```nix
services.luxnix.lxAnnotateLocal = {
  enable = cfg.lxAnnotate.enable;
  database = cfg.database;
};
```

This means that when `lx-annotate-local` is enabled through `roles.endoreg-client`, it uses `endoregDbLocal` unless the host explicitly overrides `roles.endoreg-client.database`.

## PostgreSQL Owner

The PostgreSQL database and user are owned by the NixOS `roles.postgres.default` role, not by Ansible.

Important implementation points:

- `modules/nixos/roles/postgres-default/default.nix` defines `defaultDbName = "endoregDbLocal"`.
- The role adds `endoregDbLocal` to `services.postgresql.ensureDatabases`.
- The role adds `endoregDbLocal` to `services.postgresql.ensureUsers`.
- The `postgres-endoreg-setup.service` systemd unit syncs the password from the LuxNix vault secret into PostgreSQL.

Operational checks:

```bash
systemctl status postgresql.service
systemctl status postgres-endoreg-setup.service
sudo -u postgres psql -l
sudo -u postgres psql -c '\du'
```

## What `endoreg-db-api-local` Means

`services.luxnix.endoregDbApiLocal` is the legacy/local EndoReg DB API service module.

It is not the PostgreSQL database itself. It is an application service that consumes a database config. It is disabled for normal EndoReg clients by the current `roles.endoreg-client` role:

```nix
services.luxnix.endoregDbApiLocal.enable =
  mkIf (!config.roles.endoreg-db-central-01.enable) (mkForce false);
```

Central-node roles may still configure it intentionally. Do not remove the module just because the old Ansible `local_endoreg_db` role was removed.

## Direct `lxAnnotateLocal` Use

If `services.luxnix.lxAnnotateLocal` is enabled directly, without `roles.endoreg-client`, its service-level database defaults are different:

```nix
services.luxnix.lxAnnotateLocal.database = {
  host = "lx-annotate.local";
  port = 5433;
  name = "lxAnnotateLocal";
  user = "lxAnnotateLocal";
};
```

For ordinary client hosts, prefer enabling `roles.endoreg-client.lxAnnotate.enable = true` or explicitly set `services.luxnix.lxAnnotateLocal.database` to the desired database.

## Naming Rule

Use these terms consistently:

- `endoregDbLocal`: the local PostgreSQL database/user used by EndoReg client services.
- `postgres-endoreg-setup.service`: systemd unit that ensures the local PostgreSQL user password.
- `lx-annotate-local`: the current lx-annotate service implementation.
- `endoreg-db-api-local`: legacy/local EndoReg DB API application service.
- `local_endoreg_db`: deprecated Ansible role name; do not use for current configuration.
