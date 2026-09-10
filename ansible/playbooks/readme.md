# Ansible Entry Points

Run commands from the repository root. The canonical command names and risk
classifications live in [`devenv/commands.yml`](../../devenv/commands.yml).

## Safety boundary

`check-connectivity` is read-only. `run-ansible` and `sync-secrets` can change
remote hosts and require explicit operator authorization. Their
`operator_confirmation_required` catalog field is metadata for people, agents,
and frontends; the wrappers themselves do not display a confirmation prompt.

Both wrappers refuse to run without `--limit <host-or-group>`. Use `--limit all`
only when changing every matching inventory host is deliberate and authorized.
Passing `--check --diff` previews the main playbook, but review the reported
tasks before assuming that every role supports Ansible check mode completely.

## Common workflow

1. Check SSH and remote command execution without changing the host:

   ```bash
   devenv shell check-connectivity <host-or-group>
   ```

2. Preview the main playbook against an explicit target:

   ```bash
   devenv shell run-ansible --check --diff --limit <host-or-group>
   ```

3. Review the diff, then apply by removing `--check` only when the change is
   authorized.

4. Deploy secret files separately; this is not part of the general playbook:

   ```bash
   devenv shell sync-secrets --limit <host-or-group>
   ```

The connectivity helper records operational output under `logs/`. Secret
deployment tasks use `no_log`; do not add credential values to command-line
arguments, logs, or debugging output.

## Layout

- [`../site.yml`](../site.yml): active general-purpose plays used by
  `run-ansible`.
- [`../inventory/hosts.ini`](../inventory/hosts.ini): host and group
  membership.
- [`../inventory/group_vars/README.md`](../inventory/group_vars/README.md):
  ownership and load order for shared declarative values.
- `../inventory/host_vars/`: host-specific declarative values and the primary
  Autoconf sources.
- `../roles/`: reusable task implementations selected by `site.yml`.
- [`connectivity-check.yml`](connectivity-check.yml): read-only reachability
  validation, normally invoked through `check-connectivity`.
- [`deploy_secrets.yml`](deploy_secrets.yml): dedicated sensitive deployment,
  normally invoked through `sync-secrets`.

`managed-update-luxnix.yml` is currently incomplete and has no canonical
wrapper. Do not treat it as the supported update workflow until its behavior,
risk classification, and tests are completed.
