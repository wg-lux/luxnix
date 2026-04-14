# Roles

NixOS roles are defined under `modules/nixos/roles/`. Each role is an opt-in module enabled by setting `roles.<name>.enable = true` in a host's generated `default.nix` (controlled via Ansible inventory variables).

Roles compose — higher-level roles enable lower-level ones. The typical activation chain is:

```
common
  └── postgres.default
  └── custom-packages
  └── managed-secrets
  └── system.nix / system.boot / system.locale

desktop
  └── common
  └── desktop-addons.plasma

base-server
  └── desktop
  └── custom-packages.baseDevelopment

gpu-server
  └── base-server
  └── aglnet.client
  └── custom-packages.cuda

endoreg-client
  └── desktop
  └── aglnet.client
  └── managed-secrets
```

---

## common

**Source:** `modules/nixos/roles/common/default.nix`

The foundational role included on virtually every managed host.

### Options

- `enable` — Enable common configuration.
- `packages` — Additional packages to install (default: `devenv`, `parted`, `cryptsetup`, `lsof`, `e2fsprogs`, `nix-prefetch-scripts`).

### Effects

- Installs the packages listed in `packages`.
- Disables `NetworkManager-wait-online` and `systemd-networkd-wait-online` to prevent boot delays on hosts that do not use NetworkManager.
- Enables `rtkit` for real-time scheduling priority.
- Enables `coolercontrol` for hardware thermal management.
- Creates `/etc/user-passwords` (mode 0700, owned by admin) as a secure password directory.
- Enables by default: `roles.postgres.default`, `roles.custom-packages`, `roles.managed-secrets`.
- Enables by default: `services.luxnix.podman`, `services.virtualisation.podman`.
- Enables hardware networking and graphics support.
- Sets `nixpkgs.hostPlatform` from `luxnix.generic-settings.hostPlatform`.
- Enables `cli.programs.nh`, `cli.programs.nix-ld`, `security.sops`, `programs.zsh`, `programs.command-not-found`.
- Enables `system.nix`, `system.boot`, `system.locale` (see [nix-settings.md](docs/nix-settings.md)).
- Adds the `rootIdED25519` key from generic-settings as an SSH authorized key for the admin user.

---

## desktop

**Source:** `modules/nixos/roles/desktop/default.nix`

Adds a KDE Plasma desktop environment on top of common.

### Options

- `enable` — Enable desktop configuration.

### Effects

- Enables `roles.common`.
- Enables `roles.desktop-addons.plasma` (KDE Plasma 6).
- Enables `roles.custom-packages.baseDevelopment`.
- Enables audio and Bluetooth hardware support.
- Configures binfmt for emulated systems.

### Desktop Addon — Plasma

- Enables KDE Plasma 6 desktop manager.
- Sets default session to `plasmax11`.
- Enables SDDM as display manager with GDM disabled and auto-suspend off.
- Enables X11 server with German keyboard layout (`de`).
- Installs KDE Plasma custom packages via `roles.custom-packages.kdePlasma`.

---

## base-server

**Source:** `modules/nixos/roles/base-server/default.nix`

Server profile for s-* hosts. Adds a full nix-ld library set useful for running dynamically linked binaries.

### Options

- `enable` — Enable base server configuration.

### Effects

- Enables `roles.desktop` (which pulls in `roles.common`).
- Enables `roles.custom-packages.baseDevelopment`.
- Enables SSH with `rootIdED25519` as an authorized key.
- Enables `cli.programs.nix-ld` with an extended library set (stdenv, zlib, fuse3, icu, nss, openssl, curl, CUDA runtime paths, X11 libs, etc.).
- Enables `services.virtualisation.podman` by default.
- Leaves `services.luxnix.avahi.enable = false`.

---

## gpu-server

**Source:** `modules/nixos/roles/gpu-server/default.nix`

GPU server profile for gs-* hosts.

### Options

- `enable` — Enable GPU server configuration.

### Effects

- Enables `roles.base-server` (which pulls in desktop and common).
- Enables `roles.aglnet.client` (OpenVPN VPN client).
- Enables `roles.custom-packages.cuda` (CUDA LD libraries).
- Enables `services.luxnix.endoregDbApiLocal`.

---

## endoreg-client

**Source:** `modules/nixos/roles/endoreg-client/default.nix`

Full EndoReg client workstation profile. Configures storage, AI inference services, lx-annotate, Django API, and external drive mounting.

### Options

- `enable` — Enable EndoReg client configuration.
- `adminIsServiceUser` — Whether `admin` is also the EndoReg service user (default: `true`).
- `dbApiLocal` — Enable the local `endoreg-db-api` Django service (default: `false`).
- `endoAi` — Enable the `endoAi` inference service (default: `false`).
- `defaultCenter` — Center identifier for EndoReg (default: `"university_hospital_wuerzburg"`).
- `centralNodes` — List of central node hostnames for the DB API.
- `paths` — Storage path configuration (see `paths.nix`).
- `api` — Django API configuration (see `api.nix`).
- `database` — Database connection options (see `database.nix`).
- `service` — Service runtime options (see `service.nix`).
- `repository` — Git repository options (see `repository.nix`).
- `environmentDefaults` — HuggingFace / Ollama environment defaults (see `environment-details.nix`).
- `lxAnnotate` — lx-annotate service configuration (see `lx-annotate.nix`).

### Effects

- Enables `roles.desktop`, `roles.aglnet.client`, `roles.managed-secrets`.
- Enables `roles.custom-packages.cuda`.
- Enables `luxnix.nvidia-prime`.
- Creates `user.client`, `user.endoreg-service-user`, `group.endoreg-service`.
- Enables `luxnix.storage` and `services.luxnix.fileMover`.
- Creates systemd tmpfiles for `/mnt/endoreg-sensitive-data`, `/etc/endoreg-api`, storage directories.
- Grants `admin` passwordless `mount`/`umount` via sudo.
- Sets up a periodic systemd timer to auto-mount external persisting storage drives.
- Conditionally enables `services.luxnix.endoregDbApiLocal` and `services.luxnix.lxAnnotateLocal`.
- Manages Home Manager for the `client-user` account: desktop role, symlinks for `Video_Input` and `PDF_Input` on the desktop.

---

## aglnet

**Source:** `modules/nixos/roles/` (client and host sub-roles)

OpenVPN-based private network (aglnet, subnet `172.16.255.0/24`).

### aglnet.client

#### Options

- `enable` — Enable the OpenVPN client.
- `networkName` — VPN network name.
- `mainDomain` — Main domain for the VPN.
- `port` — VPN port.
- `protocol` / `protocolLc` — Protocol (TCP/tcp by default).
- `noBind` — Add `nobind` to config.
- `restartAfterSleep` — Restart VPN after system sleep.
- `autoStart` — Autostart on boot.
- `updateResolvConf` — Update resolv.conf with VPN nameservers.
- `resolvRetry` — Resolv retry strategy (default: `"infinite"`).
- `dev` — TUN device name (default: `"tun"`).
- `subnet` / `subnetIntern` — VPN subnet.
- `keepalive` — Keepalive interval.
- `cipher` — Cipher (default: `"AES-256-GCM"`).
- `verbosity` — OpenVPN log verbosity.
- `caPath` / `tlsAuthPath` / `serverCertPath` / `serverKeyPath` — Certificate/key paths under `/etc/openvpn/`.
- `persistKey` / `persistTun` — Persist key and TUN device across restarts.

#### Effects

- Installs `openvpn`.
- Creates `/etc/openvpn` with appropriate permissions.
- Configures and enables an OpenVPN client systemd service.

### aglnet.host

The OpenVPN server role (deployed only on s-01).

#### Options

All client options plus:

- `backupNameservers` — Fallback nameservers pushed to clients.
- `dhPath` — DH parameters path.
- `clientConfigDir` — Per-client configuration directory.
- `topology` — Network topology (default: `"subnet"`).
- `client-to-client` — Allow client-to-client traffic (default: `true`).

#### Effects

- All client effects, plus:
- Configures the OpenVPN server.
- Opens firewall for VPN traffic.
- Sets backup nameservers.

---

## custom-packages

**Source:** `modules/nixos/roles/custom-packages/default.nix`

Modular package bundle. Enabled by `roles.common` with all flags off by default; individual bundles are toggled per host/group.

### Options

- `enable` — Enable the role.
- `baseDevelopment` — `nixfmt`, `vscode`, `gparted`, `keepassxc`, `vlc`, `nixd`, `fd`, `duf`, `dust`, `dysk`, `ncdu`, and more.
- `kdePlasma` — KDE Plasma support packages (`kwallet`, `systemsettings`, etc.).
- `office` — `libreoffice-qt6-fresh`, `hunspell`, `pandoc`, `obsidian`, `spotify`, `zotero`.
- `visuals` — `blender`.
- `cuda` — CUDA LD libraries (for nix-ld CUDA compatibility).
- `videoEditing` — `obs-studio`.
- `hardwareAcceleration` — `pciutils`, `libva`, `vdpauinfo`, `libva-utils`; enables `hardware.graphics` with `intel-media-driver`.
- `cloud` — `nextcloud-talk-desktop`.
- `protonmail` — `protonmail-bridge-gui`, `protonmail-desktop`, `proton-pass`, `planify`.
- `dev01` / `dev02` / `dev03` — Developer-specific bundles (currently minimal/empty except dev03: `obsidian`, `balena-cli`).
- `ld.enable` — Enable `nix-ld` (default: `true`).

### Effects

- Adds selected package bundles to `environment.systemPackages`.
- If both podman and NVIDIA are enabled, adds `nvidia-container-toolkit` and `cudatoolkit`.
- Manages `cli.programs.nix-ld` with the selected LD libraries.
- Always includes: `bash`, `bashInteractive`, `iftop`, `bmon`, `nload`, `gh`.

---

## hetzner

**Source:** `modules/nixos/roles/hetzner/` (or `modules/home/roles/hetzner/`)

Hetzner dedicated server role. Applied to h-* hosts via the `[hetzner_server]` inventory group.

### Options

- `enable` — Enable Hetzner server settings.

### Effects

- Sets the OpenSSH RSA host key path specific to Hetzner deployments.
- Applies any Hetzner-specific network/hardware configuration.

---

## managed-secrets

**Source:** `modules/nixos/roles/managed-secrets/default.nix`

Manages vault secrets deployment on the host. Enabled by default via `roles.common`.

### Effects

- Ensures vault secrets from `/home/admin/.lxv/deploy/<hostname>/` are available at `/etc/secrets/vault/`.
- Runs a one-shot `managed-secrets-setup.service` at boot to deploy secrets.

---

## postgres.default

**Source:** `modules/nixos/roles/postgres-default/default.nix`

Minimal PostgreSQL client/default configuration, enabled by default via `roles.common`.

---

## postgres-main (postgres host)

**Source:** `modules/nixos/roles/postgres-main/default.nix`

Full PostgreSQL server configuration. Deployed on gs-02 (primary) and s-04 (test).

---

## endoreg-db-central-01

**Source:** `modules/nixos/roles/endoreg-db-central-01/default.nix`

Central EndoReg database server role (s-04).

---

## nginx-host

**Source:** `modules/nixos/roles/nginx-host/default.nix`

Nginx reverse proxy role (s-02).

---

## keycloak_host

**Source:** `modules/nixos/roles/keycloak_host/default.nix`

Keycloak authentication server role (s-02).

---

## nextcloud-host / nextcloud-client

**Source:** `modules/nixos/roles/nextcloud-host/`, `modules/nixos/roles/nextcloud-client/`

Nextcloud server (s-03) and per-host Nextcloud client configuration.

---

## traefik-host

**Source:** `modules/nixos/roles/traefik-host/default.nix`

Traefik reverse proxy role.

---

## lx-anonymizer

**Source:** `modules/nixos/roles/lx-anonymizer/default.nix`

Data anonymization service role for EndoReg workflow hosts.

---

## gpu-client-dev

**Source:** `modules/nixos/roles/gpu-client-dev/default.nix`

GPU client development variant role.

---

## Inventory key reference

The following keys in `host_roles` / `group_roles` map directly to role options:

| Ansible key                                | NixOS option                              |
|--------------------------------------------|-------------------------------------------|
| `common.enable`                            | `roles.common.enable`                     |
| `base_server.enable`                       | `roles.base-server.enable`                |
| `aglnet.client.enable`                     | `roles.aglnet.client.enable`              |
| `endoreg_client.enable`                    | `roles.endoreg-client.enable`             |
| `hetzner.enable`                           | `roles.hetzner.enable`                    |
| `custom_packages.enable`                   | `roles.custom-packages.enable`            |
| `custom_packages.baseDevelopment`          | `roles.custom-packages.baseDevelopment`   |
| `custom_packages.office`                   | `roles.custom-packages.office`            |
| `custom_packages.visuals`                  | `roles.custom-packages.visuals`           |
| `custom_packages.cuda`                     | `roles.custom-packages.cuda`              |
| `custom_packages.videoEditing`             | `roles.custom-packages.videoEditing`      |
| `custom_packages.hardwareAcceleration`     | `roles.custom-packages.hardwareAcceleration` |
| `custom_packages.cloud`                    | `roles.custom-packages.cloud`             |

Note: Ansible uses underscores; the generated Nix uses hyphens and dots. The autoconf pipeline handles the mapping automatically.
