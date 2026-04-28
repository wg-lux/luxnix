# PostgreSQL Local Setup for lx-annotate in LuxNix

## Overview
This historical note describes the old local PostgreSQL setup work for `lx-annotate`.

For the current ownership model, start with [Database Ownership and Legacy Names](docs/database-ownership.md). The current EndoReg client path uses `roles.endoreg-client.database`, whose default database/user is `endoregDbLocal`.

---

## Steps Completed

### 1. PostgreSQL User and Database
- Current client default: `endoregDbLocal` database and `endoregDbLocal` user.
- Owner: `modules/nixos/roles/postgres-default/default.nix`.
- Password source: `/etc/secrets/vault/SCRT_local_password_maintenance_password`.
- Systemd setup unit: `postgres-endoreg-setup.service`.
- Historical names such as `lxAnnotateDb`, `lxAnnotateUser`, and `postgres-lx-annotate-setup` should not be used for new host configuration unless a host deliberately opts into a separate lx-annotate database.

### 2. Create a System User for lx-annotate
- Defined in `modules/nixos/user/lx-annotate-service-user/default.nix`.
- User: `lx-annotate-service-user`, group: `lx-annotate-service`, home: `/var/lx-annotate-service-user`.

### 3. Create the Service Module for lx-annotate
- Created `modules/nixos/services/lx-annotate/default.nix`.
- Clones and updates the `lx-annotate` repo from `https://github.com/wg-lux/lx-annotate.git`.
- Injects DB config (with password) into the app.
- Runs as `lx-annotate-service-user`.
- Systemd service ensures correct startup order and dependencies.

### 4. Enable the Service/Role on Host `gc-08`
- In `systems/x86_64-linux/gc-08/default.nix`:
  ```nix
  services.luxnix.lxAnnotateLocal.enable = true;
  ```
- Rebuild with `sudo nixos-rebuild switch`.

---

## How to Enable on Additional Hosts

1. Open the config file for the target host, e.g.:
   `/home/admin/dev/luxnix/systems/x86_64-linux/<host>/default.nix`
2. Add or merge the following lines:
   ```nix
   services.luxnix.lxAnnotateLocal.enable = true;
   ```
3. Run `sudo nixos-rebuild switch` on the new host.

---

## Validation & Troubleshooting

- Check user: `id lx-annotate-service-user`
- Check service: `systemctl status lx-annotate`
- Check DB setup: `systemctl status postgres-endoreg-setup.service`
- Check password file: `sudo cat /etc/secrets/vault/SCRT_local_password_maintenance_password`
- Test DB connection as `endoregDbLocal` to `endoregDbLocal`.

---

## Security & Permissions
- Password file is only readable by root and the sensitive group.
- Service user runs with least privilege.
- DB access is local-only by default (localhost).

---

## Summary Table
| Step | File | Description |
|------|------|-------------|
| 1 | modules/nixos/roles/postgres-default/default.nix | Own `endoregDbLocal` DB/user and password sync |
| 2 | modules/nixos/user/lx-annotate-service-user/default.nix | System user definition |
| 3 | modules/nixos/services/lx-annotate/default.nix | Service module |
| 4 | systems/x86_64-linux/gc-08/default.nix | Host enablement |

---

## FAQ & Details

### Does it clone the repo? Where is it saved?
- Yes, the lx-annotate service module clones the repository from `https://github.com/wg-lux/lx-annotate.git`.
- The repo is saved in the home directory of the service user: `/var/lx-annotate-service-user/lx-annotate`.

### How are passwords managed?
- A secure password for the PostgreSQL user `endoregDbLocal` is generated or reused from `/etc/secrets/vault/SCRT_local_password_maintenance_password`.
- The password is injected into the app config for DB connection.
- Permissions are set so only root and the sensitive group can read the password file.

### What are the steps to run it?
1. Enable the user and service in the host config.
2. Run `sudo nixos-rebuild switch`.
3. The system will:
   - Create the DB and user in PostgreSQL
   - Generate and sync the password
   - Clone/update the repo
   - Inject DB config
   - Start the app as a systemd service

### If the same repo is already present, what happens?
- The service will update the existing repo by fetching and pulling the latest changes from the specified branch.
- It will not reclone or overwrite untracked files, but will keep the repo up to date.

### What is the name of the database installed locally for lx-annotate?
- Current EndoReg client default: `endoregDbLocal`.
- Direct `services.luxnix.lxAnnotateLocal` use has service-level defaults named `lxAnnotateLocal`, but the preferred client path overrides those via `roles.endoreg-client.database`.

---

## Notes
- To enable on more hosts, repeat the host config step above.
- For further troubleshooting, see `postgres-documentation.md` and system logs.
