# Systems

_Auto-generated from `autoconf/merged_vars/` and `systems/x86_64-linux/`
by `scripts/generate-systems-doc.py`._

_Re-run after `devenv tasks run autoconf:finished` to pick up inventory changes._
_Free-text notes between `<!-- notes:X -->` and `<!-- end-notes:X -->` are preserved.
Edit them directly in this file._

---

## Fleet summary

| Host | Type | VPN IP | CPU | GPU | Auto-updates |
|------|------|--------|-----|-----|--------------|
| [s-01](#s-01) | Base server (OpenVPN host) | `172.16.255.1` | amd | — | ✗ |
| [s-02](#s-02) | Base server (nginx / keycloak) | `172.16.255.12` | intel | — | ✗ |
| [s-03](#s-03) | Base server (nextcloud) | `172.16.255.13` | amd | — | ✗ |
| [s-04](#s-04) | Base server (central DB) | `172.16.255.14` | intel | — | ✗ |
| [gs-01](#gs-01) | GPU server | `172.16.255.21` | amd | NVIDIA production | ✓ |
| [gs-02](#gs-02) | GPU server (primary PostgreSQL) | `172.16.255.22` | amd | NVIDIA production | ✓ |
| [gc-01](#gc-01) | GPU client workstation | `172.16.255.101` | — | NVIDIA production PRIME | ✗ |
| [gc-02](#gc-02) | GPU client workstation | `172.16.255.102` | intel | NVIDIA production PRIME | ✗ |
| [gc-03](#gc-03) | GPU client workstation | `172.16.255.103` | — | NVIDIA production PRIME | ✗ |
| [gc-04](#gc-04) | GPU client workstation | `172.16.255.104` | intel | NVIDIA production PRIME | ✗ |
| [gc-05](#gc-05) | GPU client workstation | `172.16.255.105` | intel | NVIDIA production PRIME | ✗ |
| [gc-06](#gc-06) | GPU client workstation | `172.16.255.106` | intel | NVIDIA production PRIME | ✗ |
| [gc-07](#gc-07) | GPU client workstation | `172.16.255.107` | intel | NVIDIA production PRIME | ✗ |
| [gc-08](#gc-08) | GPU client workstation | `172.16.255.108` | intel | NVIDIA production PRIME | ✗ |
| [gc-09](#gc-09) | GPU client workstation | `172.16.255.109` | intel | NVIDIA production PRIME | ✗ |
| [gc-10](#gc-10) | GPU client workstation | `172.16.255.110` | intel | NVIDIA production PRIME | ✗ |
| [c-01](#c-01) | Client host | `172.16.255.131` | intel | — | ✗ |
| [h-01](#h-01) | Hetzner dedicated server | `172.16.255.201` | amd | — | ✗ |

---

## s-01

**Type:** Base server (OpenVPN host)
**VPN IP:** `172.16.255.1`
**Local IP:** `192.168.179.1`
**Domains:** `s-01.intern`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `amd` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-amd` |

### Enabled roles

- `aglnet.host`
- `base-server`
- `common`
- `custom-packages`

**Explicitly disabled:**

- `aglnet.client`
- `endoreg-client`

**Custom package bundles:**

- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:s-01 -->
_No notes yet._
<!-- end-notes:s-01 -->

---

## s-02

**Type:** Base server (nginx / keycloak)
**VPN IP:** `172.16.255.12`
**Local IP:** `192.168.179.2`
**Domains:** `nginx.endo-reg.net`, `cloud.endo-reg.net`, `keycloak.endo-reg.net`, `s-02.intern`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `intel` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-intel` |

### Enabled roles

- `aglnet.client`
- `base-server`
- `common`
- `custom-packages`
- `keycloakHost`
- `nginxHost`
- `postgres.main`

**Explicitly disabled:**

- `endoreg-client`

**Custom package bundles:**

- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:s-02 -->
_No notes yet._
<!-- end-notes:s-02 -->

---

## s-03

**Type:** Base server (nextcloud)
**VPN IP:** `172.16.255.13`
**Local IP:** `192.168.179.3`
**Domains:** `s-03.intern`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `amd` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-amd` |

### Enabled roles

- `aglnet.client`
- `base-server`
- `common`
- `custom-packages`
- `nextcloudHost`

**Explicitly disabled:**

- `endoreg-client`
- `postgres.default`

**Custom package bundles:**

- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:s-03 -->
_No notes yet._
<!-- end-notes:s-03 -->

---

## s-04

**Type:** Base server (central DB)
**VPN IP:** `172.16.255.14`
**Local IP:** `192.168.0.194`
**Domains:** `s-04.intern`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `intel` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-intel` |

### Enabled roles

- `aglnet.client`
- `base-server`
- `common`
- `custom-packages`
- `endoreg-client`
- `endoreg-db-central-01`
- `postgres.default`
- `ssh-access.dev-01`
- `ssh-access.dev-03`
- `ssh-access.dev-04`
- `ssh-access.dev_01`
- `ssh-access.dev_03`
- `ssh-access.dev_04`

**Custom package bundles:**

- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:s-04 -->
_No notes yet._
<!-- end-notes:s-04 -->

---

## gs-01

**Type:** GPU server
**VPN IP:** `172.16.255.21`
**Local IP:** `192.168.0.228`
**Domains:** `gs-01.intern`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `amd` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-amd` |
| NVIDIA GPU | `production` driver |

### Enabled roles

- `aglnet.client`
- `base-server`
- `common`
- `custom-packages`
- `endoreg-client`
- `gpu-server`
- `postgres.default`
- `ssh-access.dev-01`
- `ssh-access.dev-03`
- `ssh-access.dev-04`
- `ssh-access.dev_01`
- `ssh-access.dev_03`
- `ssh-access.dev_04`

**Custom package bundles:**

- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | **enabled** |
| Update time  | `17:00` |
| Flake target | `github:wg-lux/luxnix/prototype` |

### Notes

<!-- notes:gs-01 -->
_No notes yet._
<!-- end-notes:gs-01 -->

---

## gs-02

**Type:** GPU server (primary PostgreSQL)
**VPN IP:** `172.16.255.22`
**Local IP:** `192.168.0.56`
**Domains:** `gs-02.intern`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `amd` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-amd` |
| NVIDIA GPU | `production` driver |

### Enabled roles

- `aglnet.client`
- `base-server`
- `common`
- `custom-packages`
- `endoreg-client`
- `gpu-server`
- `postgres.default`
- `ssh-access.dev-01`
- `ssh-access.dev-03`
- `ssh-access.dev-04`
- `ssh-access.dev_01`
- `ssh-access.dev_03`
- `ssh-access.dev_04`

**Custom package bundles:**

- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | **enabled** |
| Update time  | `17:00` |
| Flake target | `github:wg-lux/luxnix/prototype` |

### Notes

<!-- notes:gs-02 -->
_No notes yet._
<!-- end-notes:gs-02 -->

---

## gc-01

**Type:** GPU client workstation
**VPN IP:** `172.16.255.101`
**Domains:** `gc-01.intern`, `lx-annotate.local`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| NVIDIA GPU | `production` driver |

### Enabled roles

- `aglnet.client`
- `common`
- `custom-packages`
- `endoreg-client`
- `nextcloudClient`

**Custom package bundles:**

- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:gc-01 -->
_No notes yet._
<!-- end-notes:gc-01 -->

---

## gc-02

**Type:** GPU client workstation
**VPN IP:** `172.16.255.102`
**Domains:** `gc-02.intern`, `lx-annotate.local`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `intel` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-intel` |
| NVIDIA GPU | `production` driver |
| NVIDIA PRIME | nvidia `PCI:1:0:0` + intel `PCI:0:2:0` |

### Enabled roles

- `aglnet.client`
- `common`
- `custom-packages`
- `endoreg-client`
- `nextcloudClient`
- `postgres.default`

**Custom package bundles:**

- `baseDevelopment`
- `cloud`
- `hardwareAcceleration`
- `videoEditing`
- `visuals`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:gc-02 -->
_No notes yet._
<!-- end-notes:gc-02 -->

---

## gc-03

**Type:** GPU client workstation
**VPN IP:** `172.16.255.103`
**Domains:** `gc-03.intern`, `lx-annotate.local`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| NVIDIA GPU | `production` driver |

### Enabled roles

- `aglnet.client`
- `common`
- `custom-packages`
- `endoreg-client`
- `nextcloudClient`

**Custom package bundles:**

- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:gc-03 -->
_No notes yet._
<!-- end-notes:gc-03 -->

---

## gc-04

**Type:** GPU client workstation
**VPN IP:** `172.16.255.104`
**Domains:** `gc-04.intern`, `lx-annotate.local`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `intel` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-intel` |
| NVIDIA GPU | `production` driver |
| NVIDIA PRIME | nvidia `PCI:1:0:0` + intel `PCI:0:2:0` |

### Enabled roles

- `aglnet.client`
- `common`
- `custom-packages`
- `endoreg-client`
- `nextcloudClient`
- `ssh-access.dev-01`
- `ssh-access.dev-03`
- `ssh-access.dev-04`
- `ssh-access.dev_01`
- `ssh-access.dev_03`
- `ssh-access.dev_04`

**Custom package bundles:**

- `baseDevelopment`
- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:gc-04 -->
_No notes yet._
<!-- end-notes:gc-04 -->

---

## gc-05

**Type:** GPU client workstation
**VPN IP:** `172.16.255.105`
**Domains:** `gc-05.intern`, `lx-annotate.local`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `intel` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-intel` |
| NVIDIA GPU | `production` driver |
| NVIDIA PRIME | nvidia `PCI:1:0:0` + intel `PCI:0:2:0` |

### Enabled roles

- `aglnet.client`
- `common`
- `custom-packages`
- `endoreg-client`
- `nextcloudClient`
- `postgres.default`
- `ssh-access.dev-01`
- `ssh-access.dev-03`
- `ssh-access.dev-04`

**Custom package bundles:**

- `baseDevelopment`
- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:gc-05 -->
_No notes yet._
<!-- end-notes:gc-05 -->

---

## gc-06

**Type:** GPU client workstation
**VPN IP:** `172.16.255.106`
**Local IP:** `172.31.179.8`
**Domains:** `gc-06.intern`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `intel` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-intel` |
| NVIDIA GPU | `production` driver |
| NVIDIA PRIME | nvidia `PCI:1:0:0` + intel `PCI:0:2:0` |

### Enabled roles

- `aglnet.client`
- `common`
- `custom-packages`
- `endoreg-client`
- `nextcloudClient`
- `postgres.default`

**Custom package bundles:**

- `baseDevelopment`
- `cloud`
- `hardwareAcceleration`
- `protonmail`
- `videoEditing`
- `visuals`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:gc-06 -->
_No notes yet._
<!-- end-notes:gc-06 -->

---

## gc-07

**Type:** GPU client workstation
**VPN IP:** `172.16.255.107`
**Domains:** `gc-07.intern`, `lx-annotate.local`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `intel` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `intel` |
| NVIDIA GPU | `production` driver |
| NVIDIA PRIME | nvidia `PCI:1:0:0` + intel `PCI:0:2:0` |

### Enabled roles

- `aglnet.client`
- `common`
- `custom-packages`
- `endoreg-client`
- `nextcloudClient`
- `postgres.default`

**Custom package bundles:**

- `baseDevelopment`
- `cloud`
- `cuda`
- `office`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:gc-07 -->
_No notes yet._
<!-- end-notes:gc-07 -->

---

## gc-08

**Type:** GPU client workstation
**VPN IP:** `172.16.255.108`
**Domains:** `gc-08.intern`, `lx-annotate.local`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `intel` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `intel` |
| NVIDIA GPU | `production` driver |
| NVIDIA PRIME | nvidia `PCI:1:0:0` + intel `PCI:0:2:0` |

### Enabled roles

- `aglnet.client`
- `common`
- `custom-packages`
- `endoreg-client`
- `nextcloudClient`
- `postgres.default`

**Custom package bundles:**

- `baseDevelopment`
- `cloud`
- `cuda`
- `dev03`
- `office`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:gc-08 -->
_No notes yet._
<!-- end-notes:gc-08 -->

---

## gc-09

**Type:** GPU client workstation
**VPN IP:** `172.16.255.109`
**Domains:** `gc-09.intern`, `lx-annotate.local`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `intel` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-intel` |
| NVIDIA GPU | `production` driver |
| NVIDIA PRIME | nvidia `PCI:1:0:0` + intel `PCI:0:2:0` |

### Enabled roles

- `aglnet.client`
- `common`
- `custom-packages`
- `endoreg-client`
- `nextcloudClient`
- `postgres.default`
- `ssh-access.dev-01`
- `ssh-access.dev-03`
- `ssh-access.dev-04`
- `ssh-access.dev_01`
- `ssh-access.dev_03`
- `ssh-access.dev_04`

**Custom package bundles:**

- `baseDevelopment`
- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:gc-09 -->
_No notes yet._
<!-- end-notes:gc-09 -->

---

## gc-10

**Type:** GPU client workstation
**VPN IP:** `172.16.255.110`
**Domains:** `gc-10.intern`, `lx-annotate.local`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `intel` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-intel` |
| NVIDIA GPU | `production` driver |
| NVIDIA PRIME | nvidia `PCI:1:0:0` + intel `PCI:0:2:0` |

### Enabled roles

- `aglnet.client`
- `common`
- `custom-packages`
- `endoreg-client`
- `nextcloudClient`
- `postgres.default`
- `ssh-access.dev-01`
- `ssh-access.dev-03`
- `ssh-access.dev-04`
- `ssh-access.dev_01`
- `ssh-access.dev_03`
- `ssh-access.dev_04`

**Custom package bundles:**

- `baseDevelopment`
- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:gc-10 -->
_No notes yet._
<!-- end-notes:gc-10 -->

---

## c-01

**Type:** Client host
**VPN IP:** `172.16.255.131`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `intel` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-intel` |

### Enabled roles

- `aglnet.client`
- `common`
- `custom-packages`
- `desktop`

**Custom package bundles:**

- `cloud`
- `hardwareAcceleration`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:c-01 -->
_No notes yet._
<!-- end-notes:c-01 -->

---

## h-01

**Type:** Hetzner dedicated server
**VPN IP:** `172.16.255.201`

### Hardware

| Property | Value |
|----------|-------|
| Platform | `x86_64-linux` |
| State version | `23.11` |
| CPU microcode | `amd` |
| Kernel packages | `pkgs.linuxPackages_6_6` |
| Kernel modules | `kvm-amd` |

### Enabled roles

- `aglnet.host`
- `common`
- `custom-packages`
- `roles.hetzner`

**Explicitly disabled:**

- `aglnet.client`

**Custom package bundles:**

- `cloud`

### Maintenance

| Property | Value |
|----------|-------|
| Auto-updates | disabled |

### Notes

<!-- notes:h-01 -->
_No notes yet._
<!-- end-notes:h-01 -->

---
