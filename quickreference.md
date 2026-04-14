# LuxNix Quick Reference

Use-case index for humans and AI agents. Find the right documentation section without reading every guide.

---

## "I want to..." — scenario index

### Deploy and provision

| Scenario | Go to |
|---|---|
| Install NixOS on a machine for the first time | [docs/getting-started.md](docs/getting-started.md) — Day-0 flow |
| Deploy an existing host config to a freshly installed machine | [docs/deployment-guide.md](docs/deployment-guide.md) |
| Deploy to a Hetzner dedicated server | [scripts/hetzner-remote-install.sh](scripts/hetzner-remote-install.sh), [roles-documentation.md § hetzner](roles-documentation.md#hetzner) |
| Apply a config change to a running host | `nh os switch` (see [LxCheatsheet.md](LxCheatsheet.md)) |
| Apply a home-manager change | `nh home switch` (see [LxCheatsheet.md](LxCheatsheet.md)) |
| Validate a host config before deploying | `nix eval ".#nixosConfigurations.<host>.config.system.build.toplevel.drvPath"` |
| Check which hosts are in the flake outputs | `nix eval --json --expr 'builtins.attrNames (builtins.getFlake (toString ./.)).nixosConfigurations' \| jq -r '.[]'` |

---

### Add or change hosts

| Scenario | Go to |
|---|---|
| Add a brand-new host to the fleet | [docs/ansible-workflow.md § Adding a new host](docs/ansible-workflow.md#workflow-adding-a-new-host) |
| Create `disks.nix` for a new host | [docs/hardware-setup.md](docs/hardware-setup.md) — use an existing host as a reference |
| Set a host's IP address | [docs/ansible-workflow.md § IP addressing](docs/ansible-workflow.md#ip-addressing-reference) + `group_vars/all.yml` network hosts block |
| Change a host's hostname | Rename in `hosts.ini`, rename `host_vars/<old>.yml` → `host_vars/<new>.yml`, re-run autoconf |
| Understand what VPN IP a host has | [docs/ansible-workflow.md § IP addressing](docs/ansible-workflow.md#ip-addressing-reference) |

---

### Configure roles and packages

| Scenario | Go to |
|---|---|
| Enable a role for one host | [docs/ansible-workflow.md § Enabling a role](docs/ansible-workflow.md#workflow-adding-a-role-to-an-existing-host) |
| Enable a role for a whole group | Add to `group_vars/<group>.yml` under `group_roles:` |
| See what a role actually does | [roles-documentation.md](roles-documentation.md) |
| Add a package bundle (office, dev tools, CUDA…) | [roles-documentation.md § custom-packages](roles-documentation.md#custom-packages), then set `custom_packages.<bundle>: "true"` in `host_roles` |
| Enable NVIDIA GPU / PRIME | [docs/ansible-workflow.md § GPU settings](docs/ansible-workflow.md#gpu) + `host_vars/<host>.yml` |
| Understand what `roles.common` enables | [roles-documentation.md § common](roles-documentation.md#common) |
| Understand role composition / activation chain | [roles-documentation.md](roles-documentation.md) — top-level role tree diagram |

---

### Configure the Ansible inventory

| Scenario | Go to |
|---|---|
| Understand the variable merge order | [docs/ansible-workflow.md § How configuration is structured](docs/ansible-workflow.md#how-configuration-is-structured) |
| Add or change a `group_luxnix` / `host_luxnix` setting | [docs/ansible-workflow.md § Variable reference](docs/ansible-workflow.md#variable-reference) |
| Know which key to use for kernel modules, CPU microcode, etc. | [docs/ansible-workflow.md § Linux kernel](docs/ansible-workflow.md#linux-kernel) |
| Add a new inventory group | [docs/ansible-workflow.md § Adding a new group](docs/ansible-workflow.md#workflow-adding-a-new-group) |
| Understand the `[group_home_*]` groups | [docs/ansible-workflow.md § Home-manager groups](docs/ansible-workflow.md#home-manager-groups) |
| Map an Ansible key to its NixOS option name | [roles-documentation.md § Inventory key reference](roles-documentation.md#inventory-key-reference) |

---

### Regenerate NixOS configs

| Scenario | Go to |
|---|---|
| Regenerate all `systems/*/default.nix` files | `devenv tasks run autoconf:finished` |
| Understand how Ansible vars become `default.nix` | [docs/lx-administration.md](docs/lx-administration.md) — full pipeline walkthrough |
| See a summary of all hosts and their roles | [docs/systems.md](docs/systems.md) |
| Inspect what a host's merged config looks like | `autoconf/merged_vars/<hostname>.yml` (after running the pipeline) |
| Debug why a generated file looks wrong | [docs/lx-administration.md § Debugging](docs/lx-administration.md#debugging) |
| Edit a host's `default.nix` directly | **Don't.** Edit `host_vars/<host>.yml` and re-run autoconf. `systems/*/default.nix` is always overwritten. |
| Understand the Jinja2 template variables | [docs/lx-administration.md § Template system](docs/lx-administration.md#template-system) |
| Understand `home_only_hosts` / home-only pipeline | [docs/lx-administration.md § Home-only hosts](docs/lx-administration.md#home-only-hosts) |

---

### Secrets and vault

| Scenario | Go to |
|---|---|
| Bootstrap the vault on a new control machine | [docs/vault-setup.md](docs/vault-setup.md) |
| Export secrets for deployment to a host | `devenv run vault-bootstrap -- --export` ([docs/vault-setup.md](docs/vault-setup.md)) |
| Understand the vault directory layout (`~/.lxv/`) | [docs/vault-setup.md § Vault building blocks](docs/vault-setup.md#vault-building-blocks) |
| Add extra secret names to a host | `extra_secret_names:` in `host_vars/<host>.yml` |
| Understand how secrets reach `/etc/secrets/vault/` | [roles-documentation.md § managed-secrets](roles-documentation.md#managed-secrets) |

---

### Disk encryption (LUKS)

| Scenario | Go to |
|---|---|
| Set up LUKS boot decryption via USB stick | [docs/security.md](docs/security.md) |
| Understand `boot-decryption-config.nix` | [docs/security.md](docs/security.md) — LUKS key management section |
| Manage LUKS keyslots | [docs/security.md § LUKS Encryption Management](docs/security.md#luks-encryption-management) |

---

### NixOS system settings

| Scenario | Go to |
|---|---|
| Understand what `system.nix.enable` configures | [docs/nix-settings.md § system.nix](docs/nix-settings.md#systemnix--nix-daemon-settings) |
| Change trusted Nix users | [docs/nix-settings.md § Trusted users](docs/nix-settings.md#trusted-users) — edit `modules/nixos/system/nix/default.nix` |
| Understand the boot loader configuration | [docs/nix-settings.md § system.boot](docs/nix-settings.md#systemboot--boot-loader-and-kernel-settings) |
| Change the `configurationLimit` for systemd-boot | [docs/nix-settings.md § EFI boot loader](docs/nix-settings.md#efi-boot-loader) |
| Understand locale / timezone settings | [docs/nix-settings.md § system.locale](docs/nix-settings.md#systemlocale--language-and-timezone) |
| Extend the `system.nix` module with a new option | [docs/nix-settings.md § Extending system settings](docs/nix-settings.md#extending-system-settings) |

---

### Networking and VPN

| Scenario | Go to |
|---|---|
| Understand the overall network topology | [docs/network-architecture.md](docs/network-architecture.md) |
| Restart or inspect the VPN service | `sudo systemctl restart openvpn-aglnet.service` ([LxCheatsheet.md](LxCheatsheet.md)) |
| Configure the OpenVPN host (s-01) | [roles-documentation.md § aglnet.host](roles-documentation.md#aglnethost) |
| Add a host to the VPN | Add to `[active_clients]` in `hosts.ini`, set VPN IP in `group_vars/all.yml`, enable `aglnet.client.enable` |
| Understand service host mapping (keycloak, nextcloud, psql) | `group_vars/all.yml` — `generic_settings.network.serviceHosts.*` |

---

### Services and infrastructure

| Scenario | Go to |
|---|---|
| Understand the overall service layout | [docs/service-architecture.md](docs/service-architecture.md) |
| Traefik, MinIO, Gitea, PostgreSQL, KVM details | [docs/service-architecture.md](docs/service-architecture.md) |
| Configure auto-updates on a host | `maintenance.autoUpdates.*` in `host_luxnix` or `group_luxnix` ([docs/ansible-workflow.md § Maintenance](docs/ansible-workflow.md#maintenance--auto-updates)) |
| Enable Podman containers | `services.virtualisation.podman.enable` — enabled by default via `roles.common` |
| Configure virtualisation / KVM / VFIO | [docs/virtualization-guide.md](docs/virtualization-guide.md) |

---

### Users and access

| Scenario | Go to |
|---|---|
| Understand admin / dev / client user roles | [docs/access-management.md](docs/access-management.md) |
| Add a developer SSH key to a host | [docs/user-management.md](docs/user-management.md), `authentication.dev_0X.id_ed25519_pub` in `group_vars/all.yml` |
| Understand the EndoReg service user | [roles-documentation.md § endoreg-client](roles-documentation.md#endoreg-client) |
| User management via Ansible | [docs/user-management.md](docs/user-management.md) |

---

### Troubleshooting

| Symptom | Go to |
|---|---|
| `nh os switch` fails with permission denied | [CommonErrors.md](CommonErrors.md) — use `sudo nh os switch` |
| Host is missing expected packages or services | [CommonErrors.md](CommonErrors.md) — check `default.nix`, re-run autoconf |
| `nh home switch` fails with "No home defined" | [CommonErrors.md](CommonErrors.md) — add `homes/x86_64-linux/admin@<host>/default.nix` |
| SSH / connectivity fails during deploy | [CommonErrors.md](CommonErrors.md), run `./scripts/check-connectivity.sh <host>` |
| `nix build` fails to evaluate a host config | Check `autoconf/merged_vars/<host>.yml`; look in `autoconf/logs/` |
| Generated `default.nix` is wrong or empty | [docs/lx-administration.md § Debugging](docs/lx-administration.md#debugging) |
| VPN not connecting | `sudo systemctl status openvpn-aglnet.service` — check cert paths in `aglnet_conf` |
| Boot partition full | [docs/nix-settings.md § system.boot](docs/nix-settings.md#systemboot--boot-loader-and-kernel-settings) — `configurationLimit = 5` |

---

## File map (quick lookup)

| What you're looking for | File |
|---|---|
| All hosts and their groups | `ansible/inventory/hosts.ini` |
| Fleet-wide defaults | `ansible/inventory/group_vars/all.yml` |
| Per-group config | `ansible/inventory/group_vars/<group>.yml` |
| Per-host config | `ansible/inventory/host_vars/<hostname>.yml` |
| All-hosts configuration summary | `docs/systems.md` (regenerate: `devenv tasks run docs:systems`) |
| Generated merged vars (read-only) | `autoconf/merged_vars/<hostname>.yml` |
| Generated system config (read-only) | `systems/x86_64-linux/<hostname>/default.nix` |
| Disk layout | `systems/x86_64-linux/<hostname>/disks.nix` |
| LUKS decryption config | `systems/x86_64-linux/<hostname>/boot-decryption-config.nix` |
| Home-manager config (generated, read-only) | `homes/x86_64-linux/admin@<hostname>/default.nix` |
| NixOS role modules | `modules/nixos/roles/<role-name>/default.nix` |
| Nix daemon settings module | `modules/nixos/system/nix/default.nix` |
| Boot settings module | `modules/nixos/system/boot/default.nix` |
| Locale/timezone module | `modules/nixos/system/locale/default.nix` |
| System config template (Jinja2) | `conf/nix-templates/systems/x86_64-linux/main/default.nix.j2` |
| Pipeline entry point | `scripts/autoconf-pipeline.py` |
| Vault bootstrap script | `scripts/bootstrap-lx-vault.py` |
| Hetzner install script | `scripts/hetzner-remote-install.sh` |
| Pipeline logs | `autoconf/logs/autoconf_main_pipe.log` |

---

## Key commands

```bash
# Regenerate all systems/*/default.nix from Ansible inventory
devenv tasks run autoconf:finished

# Apply NixOS config on running host
nh os switch           # alias: nho

# Apply home-manager config on running host
nh home switch         # alias: nhh

# Garbage collect
nix-collect-garbage -d

# Validate a host config (control machine)
nix eval ".#nixosConfigurations.<host>.config.system.build.toplevel.drvPath"

# Deploy to a fresh NixOS install
nixos-anywhere --flake ".#<host>" nixos@<ip>

# Check SSH connectivity
./scripts/check-connectivity.sh <host>

# Restart VPN
sudo systemctl restart openvpn-aglnet.service
```

---

## For AI agents

When asked to make a configuration change for a host:
1. Read `ansible/inventory/host_vars/<hostname>.yml` (and the relevant `group_vars/` files) to understand the current config — **not** `systems/x86_64-linux/<hostname>/default.nix`.
2. Make changes in `host_vars/` or `group_vars/`.
3. Run `devenv tasks run autoconf:finished` to regenerate.
4. Verify `autoconf/merged_vars/<hostname>.yml` and `systems/x86_64-linux/<hostname>/default.nix`.

When asked about what a host currently does: check [docs/systems.md](docs/systems.md) for a quick summary, or read `autoconf/merged_vars/<hostname>.yml` for the full merged result.

When adding a new host: follow [docs/ansible-workflow.md § Adding a new host](docs/ansible-workflow.md#workflow-adding-a-new-host) exactly — the minimum required `host_vars` fields are documented there.

When looking up a role's effects: [roles-documentation.md](roles-documentation.md) is the authoritative reference. The NixOS source is `modules/nixos/roles/<role>/default.nix`.
