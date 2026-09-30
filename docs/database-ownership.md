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
- The `postgres-endoreg-setup.service` systemd unit owns the protected application password file and synchronizes
  PostgreSQL from that file.
- The legacy `SCRT_local_password_maintenance_password` path is not an authority for this role and must not be used
  to test or reset `endoregDbLocal`.

Operational checks:

```bash
systemctl status postgresql.service
systemctl status postgres-endoreg-setup.service
sudo -u postgres psql -l
sudo -u postgres psql -c '\du'
sudo postgres-maintenance --check-endoreg-auth
```

The last check deliberately uses TCP and password authentication as
`endoregDbLocal`, using the canonical protected file. It does not test peer
authentication as the `postgres` operating-system user.

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
- `/var/lib/postgresql/endoregDbLocal.password`: canonical protected application credential; preserve it during
  activation and use it for password-authenticated diagnostics.
- `lx-annotate-local`: the current lx-annotate service implementation.
- `local_endoreg_db`: deprecated Ansible role name; do not use for current configuration.
