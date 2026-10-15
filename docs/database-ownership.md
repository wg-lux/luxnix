# Database Ownership and Legacy Names

This page documents the current ownership of the local PostgreSQL database used by `lx-annotate-local`.

## Current Model

For normal EndoReg client hosts, `lx-annotate-local` uses the database configuration from `roles.endoreg-client.database`.

The default database settings are:

```nix
roles.endoreg-client.database = {
  host = "localhost";
  port = 5432;
  name = "endoregDbLocal";
  user = "endoregDbLocal";
  applicationPasswordFile = "/var/lib/postgresql/endoregDbLocal.password";
  sslMode = "prefer";
};
```

The effective connection lives in `services.luxnix.lxAnnotateLocal.database`.
Inventories and cluster validation use its `host`, `port`, and `ownership`.
Endoreg-client, lx-annotate, and lx-ai share the option schema in
`modules/nixos/roles/endoreg-client/database.nix`; service SSL modes retain their
string type while the client role restricts them to the supported enum.
The legacy `runtime.externalServices.postgresHost` and `postgresPort` options
remain supported: they replace the standard client `localhost:5432` endpoint,
but must agree with custom role endpoints and explicit service endpoints.
Conflicting values fail evaluation instead of being hidden by `mkForce`.

`database.ownership` declares who provisions this application's database:

- `local` requires the local PostgreSQL role and orders runtime preparation,
  migrations, and application startup after its provisioning units. Database
  name/user, port, and credential path must match local provisioning.
- `external` omits those application dependencies, including for an externally
  managed database reached over loopback. Its credential file must be provisioned
  independently before runtime preparation.

For compatibility, declaring the legacy external host defaults ownership to
`external`; otherwise it defaults to `local`. Address spelling does not override
an explicit ownership declaration. gs-02 explicitly declares `local` for its
managed `127.0.0.1:5432` endpoint. A new remote endpoint configured directly through
`database.host` must also declare `ownership = "external"`.

External ownership does not disable machine-wide PostgreSQL: inventory and
profiles control that service because other applications may use it.

`database.applicationPasswordFile` is the application credential source in all
three consumers. `endoregLocalUserPasswordFile` remains a compatibility alias.
The unused `database.passwordFile` option was removed: delete that setting;
configure `applicationPasswordFile` only with an application credential, never
the former maintenance-password default. No database identity or file is renamed.

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

If `services.luxnix.lxAnnotateLocal` is enabled directly, without
`roles.endoreg-client`, its defaults follow the local PostgreSQL role.

For ordinary client hosts, prefer enabling `roles.endoreg-client.lxAnnotate.enable = true` or explicitly set `services.luxnix.lxAnnotateLocal.database` to the desired database.

For a locally provisioned central hub, explicitly align
`roles.postgres.default.defaultDbName` with the application's database name and
user (typically `endoregDbCentral`). Unsupported local combinations fail
evaluation; this change does not rename databases or rotate existing passwords.
Deployments using the former direct-service defaults must explicitly declare
their existing endpoint and ownership before activation.

Hub selection comes from inventory or `profiles.endoregCentralHub`, not the
hostname. The service's neutral `hub.enable` default is false.

## Naming Rule

Use these terms consistently:

- `endoregDbLocal`: the local PostgreSQL database/user used by EndoReg client services.
- `postgres-endoreg-setup.service`: systemd unit that ensures the local PostgreSQL user password.
- `/var/lib/postgresql/endoregDbLocal.password`: canonical protected application credential; preserve it during
  activation and use it for password-authenticated diagnostics.
- `lx-annotate-local`: the current lx-annotate service implementation.
- `local_endoreg_db`: deprecated Ansible role name; do not use for current configuration.

## gc-02 automatic collation repair

`roles.postgres.default.automaticCollationRepair` is enabled only in gc-02's
canonical inventory. The `postgresql-collation-repair.service` runs after
PostgreSQL provisioning and before local EndoReg setup. It checks the managed
databases plus `postgres` and `template1`, rebuilding user and system indexes
only when the recorded default collation version differs. It refreshes the
recorded version only after both rebuilds succeed. Matching versions are a no-op.
Database names are quoted as SQL identifiers. `template0`, unmanaged databases,
and individually versioned named collations are outside this repair's scope.

This is maintenance that can extend application startup, consume disk space,
and block database queries while rebuilding indexes. Preserve the normal backup
schedule and use a maintenance window for the first deployment. Lock waits are
limited to 30 seconds, individual statements to one hour, and the unit to two
hours. Failures remain visible and block local application setup; no version
refresh hides an incomplete repair. Databases containing collatable partition
keys or materialized views require manual review because reindexing alone cannot
repair those stored results. Remote consumers are not stopped by this unit.
See [PostgreSQL collation maintenance](https://www.postgresql.org/docs/16/sql-altercollation.html).

## Reviewed salt migration on gc-02

The automatic background migration already retries independently verified groups.
gc-02's October 12 inspection found 15 blocked groups and three pending examiner
mappings; missing source evidence and placeholder identities cannot be safely
reconstructed by NixOS. The application remains active while these await review.

`services.luxnix.lxAnnotateLocal.django.identitySaltMigrationReviewFile` optionally
passes an absolute private YAML path to the packaged command's `--review-file`
argument. Supply only reviewed evidence in the application's validated schema,
with private permissions and access for the service account. Keep the contents
out of inventory, Git, and the Nix store. An absent configured file or invalid
evidence must fail, not silently fall back. No review file is configured until
real reviewed evidence exists. This option does not replace salts, remove retiring
keys, invent identity metadata, or suppress incomplete-migration errors.

## Validation

Run `pytest tests/lx-annotate/test_database_ownership.py` for ownership, endpoint
precedence, credential aliases, conflicts and removed-option rejection. Cluster
and inventory consumers are covered in `test_lx_annotate_nix_eval_contract.py`.
The original investigation is retained in
[the ownership audit](guides/lx-annotate-configuration-ownership-audit.md).
Configuration tests do not establish cold-boot success or queued-import completion.
