# Ansible Configuration Workflow

This document covers how to manage host configurations via the Ansible inventory and how those configurations flow into generated NixOS files via the autoconf pipeline.

For how the pipeline itself works, see [lx-administration.md](./lx-administration.md).

---

## How configuration is structured

Every host's NixOS configuration is assembled from three layers that are merged in order (later layers win):

```
group_vars/all.yml          ← fleet-wide defaults for every host
       ↓
group_vars/<group>.yml      ← per-group settings (a host can be in many groups)
       ↓
host_vars/<hostname>.yml    ← host-specific overrides (highest priority)
       ↓
autoconf/merged_vars/<hostname>.yml   ← merged result (do not edit by hand)
       ↓
systems/x86_64-linux/<hostname>/default.nix   ← generated NixOS config
```

Each YAML layer uses the same top-level keys:

| Key               | Purpose                                                         |
|-------------------|-----------------------------------------------------------------|
| `group_roles` / `host_roles`     | Enable/disable NixOS role modules                   |
| `group_services` / `host_services` | Configure NixOS services                          |
| `group_luxnix` / `host_luxnix`   | Set `luxnix` module options (generic-settings, vault, etc.) |

Values use **dot-notation keys** (flattened paths into the Nix attribute set):

```yaml
host_roles:
  custom_packages.baseDevelopment: "true"
  aglnet.client.enable: "true"

host_luxnix:
  generic_settings.hostPlatform: '"x86_64-linux"'
  generic_settings.linux.cpuMicrocode: '"intel"'
```

Note that string values destined for Nix must include inner quotes where the Nix type is a string literal, e.g. `'"x86_64-linux"'`.

---

## Variable reference

### Roles (`*_roles`)

Enable NixOS role modules. Each key maps to `roles.<path>` in the generated `default.nix`.

Common role keys:

| Key                                      | Default  | Description                              |
|------------------------------------------|----------|------------------------------------------|
| `common.enable`                          | `"true"` | Common packages and base configuration   |
| `base_server.enable`                     | —        | Base server role (SSH, nix-ld, etc.)     |
| `aglnet.client.enable`                   | —        | OpenVPN client (aglnet)                  |
| `endoreg_client.enable`                  | —        | EndoReg client role                      |
| `custom_packages.enable`                 | `"true"` | Custom package bundles                   |
| `custom_packages.cloud`                  | —        | Nextcloud Talk desktop package           |
| `custom_packages.baseDevelopment`        | —        | Dev tools (vscode, nixd, keepassxc, …)   |
| `custom_packages.hardwareAcceleration`   | —        | VA-API / VDPAU packages                  |
| `custom_packages.videoEditing`           | —        | OBS Studio                               |
| `custom_packages.visuals`                | —        | Blender                                  |
| `custom_packages.office`                 | —        | LibreOffice, Zotero, Obsidian, Spotify   |
| `hetzner.enable`                         | —        | Hetzner server-specific settings         |

### Services (`*_services`)

Map to `services.<path>` in the generated config. Currently most service configuration is expressed via `luxnix` options. Add keys here for services that require direct NixOS service options.

### Luxnix generic-settings (`*_luxnix`)

These map to `luxnix.<path>` in the generated config. The most commonly used sub-namespace is `generic_settings`.

#### Host identity

| Key                                              | Example value              |
|--------------------------------------------------|----------------------------|
| `generic_settings.hostPlatform`                  | `'"x86_64-linux"'`         |
| `generic_settings.systemStateVersion`            | `'"23.11"'`                |
| `generic_settings.configurationPath`             | `'"/home/admin/dev/luxnix"'` |
| `generic_settings.configurationPathRelative`     | `'"dev/luxnix"'`           |

#### Linux kernel

| Key                                                        | Example                        |
|------------------------------------------------------------|--------------------------------|
| `generic_settings.linux.kernelPackages`                    | `"pkgs.linuxPackages_6_6"`     |
| `generic_settings.linux.cpuMicrocode`                      | `'"intel"'` / `'"amd"'`       |
| `generic_settings.linux.kernelModules`                     | `["kvm-intel"]`                |
| `generic_settings.linux.kernelParams`                      | `[]`                           |
| `generic_settings.linux.kernelModulesBlacklist`            | `[]`                           |
| `generic_settings.linux.initrd.kernelModules`              | `["nfs"]`                      |
| `generic_settings.linux.initrd.availableKernelModules`     | `["xhci_pci","ahci","nvme",…]` |
| `generic_settings.linux.initrd.supportedFilesystems`       | `["nfs"]`                      |
| `generic_settings.linux.supportedFilesystems`              | `["btrfs"]`                    |
| `generic_settings.linux.resumeDevice`                      | `'"/dev/disk/by-label/nixos"'` |

#### GPU

| Key                                              | Example value       |
|--------------------------------------------------|---------------------|
| `generic_settings.gpu.nvidia.enable`             | `"true"`            |
| `generic_settings.gpu.nvidia.driver`             | `'"production"'`    |
| `generic_settings.gpu.nvidia.prime.enable`       | `"true"`            |
| `generic_settings.gpu.nvidia.prime.nvidiaBusId`  | `'"PCI:1:0:0"'`     |
| `generic_settings.gpu.nvidia.prime.onboardBusId` | `'"PCI:0:2:0"'`     |
| `generic_settings.gpu.nvidia.prime.onboardType`  | `'"intel"'`         |

#### Maintenance / auto-updates

| Key                                    | Default value                       |
|----------------------------------------|-------------------------------------|
| `maintenance.autoUpdates.enable`       | `"true"` (set per group/host)       |
| `maintenance.autoUpdates.operation`    | `'"switch"'`                        |
| `maintenance.autoUpdates.flake`        | `'"github:wg-lux/luxnix/prototype"'`|
| `maintenance.autoUpdates.dates`        | `'"17:00"'`                         |

#### Network (set in `all.yml`, rarely overridden)

Fleet-wide network definitions live in `group_vars/all.yml` under `group_luxnix`. They define each host's VPN IP, local IP, domain names, and Syncthing ID. These are populated once and rarely changed:

```yaml
generic_settings.network.hosts.gc_02.ip_vpn: '"172.16.255.102"'
generic_settings.network.hosts.gc_02.domains:
  - "gc-02.intern"
  - "lx-annotate.local"
```

#### Vault

| Key         | Value                      |
|-------------|----------------------------|
| `vault.enable` | `"true"`                |
| `vault.dir` | `'"/etc/secrets/vault"'`   |

---

## Inventory file (`hosts.ini`)

`ansible/inventory/hosts.ini` defines all hosts and their group memberships.

### Host entry format

```ini
[all]
gc-02 ansible_host=172.16.255.102

[gpu_client]
gc-02
```

A host can appear in multiple functional groups. Group memberships determine which `group_vars/*.yml` files apply.

### Standard functional groups

| Group                   | Purpose                                          |
|-------------------------|--------------------------------------------------|
| `[base_server]`         | Servers: s-01 through s-04                       |
| `[gpu_server]`          | GPU servers: gs-01, gs-02                        |
| `[gpu_client]`          | GPU client workstations: gc-01 through gc-10     |
| `[hetzner_server]`      | Hetzner dedicated servers: h-01                  |
| `[active_clients]`      | Hosts actively being managed                     |
| `[managed]`             | Hosts under full Ansible management              |
| `[language_english]`    | Hosts with English locale                        |
| `[storage_persisting_extern]` | Hosts with persistent external storage     |
| `[core_dev_ssh_access]` | Hosts granting core developer SSH access         |
| `[openvpn_host]`        | OpenVPN server host (s-01)                       |
| `[ssl_cert]`            | Hosts requiring SSL certificates                 |
| `[nginx_host]`          | Nginx reverse proxy host (s-02)                  |
| `[keycloak_host]`       | Keycloak authentication host (s-02)              |
| `[nextcloud_host]`      | Nextcloud server (s-03)                          |
| `[endoreg_db_api_local]`| Hosts running the local EndoReg DB API           |
| `[endoreg_db_central_01]`| Central EndoReg database host (s-04)            |
| `[high_rmem_wmem]`      | Hosts with elevated socket buffer settings       |

### Home-manager groups

All hosts are also placed in `[home_config]` and the `[group_home_*]` groups. These control which home-manager module categories are included:

| Group                  | Home-manager scope       |
|------------------------|--------------------------|
| `[group_home_luxnix]`  | Luxnix home options      |
| `[group_home_roles]`   | Home roles               |
| `[group_home_cli]`     | CLI programs             |
| `[group_home_desktops]`| Desktop environments     |
| `[group_home_services]`| Home services            |
| `[group_home_editors]` | Editor configuration     |

---

## Workflow: adding a new host

### 1. Add the host to `hosts.ini`

Choose the next available IP from the appropriate range:

| Prefix | VPN IP range          |
|--------|-----------------------|
| `s-*`  | 172.16.255.1 – .14    |
| `gs-*` | 172.16.255.21 – .22   |
| `gc-*` | 172.16.255.101 – .110 |
| `h-*`  | 172.16.255.201+       |

```ini
[all]
gc-11 ansible_host=172.16.255.111   # add here

[gpu_client]
gc-11                               # add to appropriate group(s)

[active_clients]
gc-11

[home_config]
gc-11 ansible_host=172.16.255.111

[group_home_luxnix]
gc-11
# ... add to any other group_home_* groups as needed
```

### 2. Create `ansible/inventory/host_vars/<hostname>.yml`

Minimum required fields:

```yaml
# inventory/host_vars/gc-11.yml
---
template_name: "main"

host_roles:
  custom_packages.baseDevelopment: "true"

host_services: {}

host_luxnix:
  generic_settings.hostPlatform: '"x86_64-linux"'
  generic_settings.systemStateVersion: '"23.11"'

  generic_settings.linux.cpuMicrocode: '"intel"'   # or "amd"
  generic_settings.linux.kernelModules:
    - "kvm-intel"
  generic_settings.linux.initrd.availableKernelModules:
    - "xhci_pci"
    - "ahci"
    - "nvme"
    - "usb_storage"
    - "sd_mod"

  maintenance.autoUpdates.enable: "false"
```

Add GPU settings if the host has a discrete GPU:

```yaml
  generic_settings.gpu.nvidia.enable: "true"
  generic_settings.gpu.nvidia.prime.enable: "true"
  generic_settings.gpu.nvidia.prime.nvidiaBusId: '"PCI:1:0:0"'
  generic_settings.gpu.nvidia.prime.onboardBusId: '"PCI:0:2:0"'
  generic_settings.gpu.nvidia.prime.onboardType: '"intel"'
  generic_settings.gpu.nvidia.driver: '"production"'
```

### 3. Add network settings in `group_vars/all.yml`

Add the host's IP and domain entries to `group_luxnix` in `all.yml`:

```yaml
generic_settings.network.hosts.gc_11.ip_vpn: '"172.16.255.111"'
generic_settings.network.hosts.gc_11.domains:
  - "gc-11.intern"
  - "lx-annotate.local"
```

If the host has a local (LAN) IP that differs from the VPN IP, also add:

```yaml
generic_settings.network.hosts.gc_11.ip_local: '"192.168.0.X"'
```

### 4. Run the autoconf pipeline

```bash
devenv tasks run autoconf:finished
```

Verify the output:
- `autoconf/merged_vars/gc-11.yml` — inspect merged variables
- `systems/x86_64-linux/gc-11/default.nix` — inspect generated config

### 5. Add hardware-specific files manually

These files are **not generated** and must be authored for each host:

- `systems/x86_64-linux/gc-11/disks.nix` — disko disk layout
- `systems/x86_64-linux/gc-11/boot-decryption-config.nix` — LUKS USB decryption

Use an existing host as a reference (e.g. `systems/x86_64-linux/gc-02/`).

---

## Workflow: adding a role to an existing host

To enable a role that is off by default, add it to the appropriate layer:

**For a single host** — add to `host_vars/<hostname>.yml`:
```yaml
host_roles:
  custom_packages.office: "true"
```

**For a group** — add to `group_vars/<group>.yml`:
```yaml
group_roles:
  custom_packages.office: "true"
```

Then re-run the pipeline:
```bash
devenv tasks run autoconf:finished
```

Verify `systems/x86_64-linux/<hostname>/default.nix` contains the new role key, then deploy:
```bash
nh os switch   # on the target host
```

---

## Workflow: adding a new group

1. Add the group to `hosts.ini`:
   ```ini
   [my_new_group]
   gc-02
   gc-06
   ```
2. Create `ansible/inventory/group_vars/my_new_group.yml`:
   ```yaml
   group_roles:
     some_role.enable: "true"
   group_services: {}
   group_luxnix: {}
   ```
3. Run the pipeline and verify.

---

## IP addressing reference

```
172.16.255.0/24   — VPN subnet (aglnet)
  .1              — s-01
  .12             — s-02
  .13             — s-03
  .14             — s-04
  .21             — gs-01
  .22             — gs-02
  .101 – .110     — gc-01 through gc-10
  .131            — c-01
  .201            — h-01
```

---

## Tips

- **Never edit `autoconf/`** — its contents are fully regenerated on every pipeline run.
- **Never edit `systems/<host>/default.nix` by hand** — changes are overwritten by the next pipeline run. All configuration changes go into the Ansible inventory.
- `disks.nix` and `boot-decryption-config.nix` are committed manually and are safe to edit directly.
- Use `autoconf/merged_vars/<host>.yml` to verify that overrides are applied as expected before running a deploy.
