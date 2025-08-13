# PostgreSQL Local Setup for lx-annotate in LuxNix

## Overview
This document describes the steps and configuration for setting up a local PostgreSQL database for the `lx-annotate` project on a LuxNix-managed system. The setup is modular, secure, and scalable, following the same pattern as the EndoReg API.

---

## Steps Completed

### 1. Add PostgreSQL User and Database for lx-annotate
- Added `lxAnnotateDb` to `ensureDatabases` in `modules/nixos/roles/postgres-default/default.nix`.
- Added `lxAnnotateUser` to `ensureUsers` in the same file.
- Password for `lxAnnotateUser` is securely generated and stored in `/etc/secrets/vault/SCRT_local_password_lx_annotate`.
- Systemd service `postgres-lx-annotate-setup` ensures the password is set in PostgreSQL and kept in sync.

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
  user.lx-annotate-service-user.enable = true;
  services.luxnix.lxAnnotate.enable = true;
  ```
- Rebuild with `sudo nixos-rebuild switch`.

---

## How to Enable on Additional Hosts

1. Open the config file for the target host, e.g.:
   `/home/admin/dev/luxnix/systems/x86_64-linux/<host>/default.nix`
2. Add or merge the following lines:
   ```nix
   user.lx-annotate-service-user.enable = true;
   services.luxnix.lxAnnotate.enable = true;
   ```
3. Run `sudo nixos-rebuild switch` on the new host.

---

## Validation & Troubleshooting

- Check user: `id lx-annotate-service-user`
- Check service: `systemctl status lx-annotate`
- Check DB setup: `systemctl status postgres-lx-annotate-setup`
- Check password file: `sudo cat /etc/secrets/vault/SCRT_local_password_lx_annotate`
- Test DB connection as `lxAnnotateUser` to `lxAnnotateDb`.

---

## Security & Permissions
- Password file is only readable by root and the sensitive group.
- Service user runs with least privilege.
- DB access is local-only by default (localhost).

---

## Summary Table
| Step | File | Description |
|------|------|-------------|
| 1 | modules/nixos/roles/postgres-default/default.nix | Add DB/user, password logic |
| 2 | modules/nixos/user/lx-annotate-service-user/default.nix | System user definition |
| 3 | modules/nixos/services/lx-annotate/default.nix | Service module |
| 4 | systems/x86_64-linux/gc-08/default.nix | Host enablement |

---

## FAQ & Details

### Does it clone the repo? Where is it saved?
- Yes, the lx-annotate service module clones the repository from `https://github.com/wg-lux/lx-annotate.git`.
- The repo is saved in the home directory of the service user: `/var/lx-annotate-service-user/lx-annotate`.

### How are passwords managed?
- A secure password for the PostgreSQL user `lxAnnotateUser` is generated (if missing) and stored in `/etc/secrets/vault/SCRT_local_password_lx_annotate`.
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
- The database name is `lxAnnotateDb` (as set in the NixOS service and DB config).

---

## Notes
- To enable on more hosts, repeat the host config step above.
- For further troubleshooting, see `postgres-documentation.md` and system logs.
