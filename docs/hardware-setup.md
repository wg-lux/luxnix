# Hardware Setup

This document covers hardware prerequisites and host-specific files required before deployment.

## Prerequisites

- UEFI-capable system
- At least one storage device (NVMe or SATA)
- Optional USB stick for boot decryption
- Optional FIDO2 key

Check UEFI mode:

```bash
[ -d /sys/firmware/efi ] && echo "UEFI" || echo "BIOS"
```

## Required LuxNix files per host

Each target host should have:

```text
systems/x86_64-linux/<host>/
├── default.nix
├── disks.nix
└── hardware-configuration.nix
```

And matching home config:

```text
homes/x86_64-linux/admin@<host>/default.nix
```

## Hardware-configuration workflow

1. Boot installer on target machine.
2. Run:

```bash
sudo nixos-generate-config
cat /etc/nixos/hardware-configuration.nix
```

3. Copy relevant hardware fields into:
   - `systems/x86_64-linux/<host>/hardware-configuration.nix`

## Disk setup validation

On target machine:

```bash
lsblk
```

Then verify:

- Device paths in `disks.nix` are correct
- Partitioning/encryption layout matches your intent

## First rebuild commands

Use canonical commands first:

```bash
nh os switch
nh home switch
```

Alias equivalents:

- `nho` -> `nh os switch`
- `nhh` -> `nh home switch`

## Password/secret path note

If your setup uses managed admin passwords, follow [Vault Setup](./vault-setup.md).
Do not rely on undocumented local paths like `etc/user-password/files`.

## Boot decryption setup

To configure boot decryption USB support, follow:

- [Security: Boot Decryption USB Stick Setup](./security.md#boot-decryption-usb-stick-setup)

## Next steps

- Continue with [Deployment Guide](./deployment-guide.md)
- Run preflight checks from [Getting Started](./getting-started.md#preflight-checklist)
