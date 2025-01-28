# Hardware Setup

## Overview

This document outlines the hardware setup required for LuxNix, including disk encryption, boot configuration, and hardware-specific settings.

## Prerequisites

Before beginning setup, ensure you have:

- ### A computer with UEFI boot support

#### Check if your system is booted in UEFI mode
```bash
[ -d /sys/firmware/efi ] && echo "UEFI" || echo "BIOS"
```

#### For more details
```bash
ls /sys/firmware/efi/efivars
```

- ### At least one storage device (NVMe or SATA)
- ### (Optional) USB stick for boot decryption
- ### (Optional) FIDO2 security key for enhanced security

## Storage Configuration

### Disk Layout
The standard disk layout for LuxNix requires:
1. EFI System Partition (ESP)
   - Size: 512MB minimum
   - Format: FAT32
   - Mount point: `/boot`

2. Root Partition
   - Size: Remaining space
   - Format: LUKS2 encrypted ext4
   - Mount point: Various (see below)

### Mount Points
The system uses an [impermanence setup](security.md#luks-encryption-management) with the following mount points:
- `/` (root)
- `/home`
- `/nix`
- `/nix/store`
- `/persist`
- `/var/log`

## Hardware-Specific Configuration

You can download the LuxNix Github repository after Nix installation and correct partition through the terminal.

For this, do:

```bash

git clone https://github.com/wg-lux/luxnix
cd luxnix
```

The machine will update with:
```bash
nho
```

CAUTION: Before restarting and rebuilding make sure you have a hashed password file on your machine at 

etc/user-password/files

---

## Essential Files and Directories

### Ansible Configuration
1. **Inventory File (`hosts.ini`):**
   - Lists hosts and their roles (e.g., servers, GPU clients).
   - Example:
     ```ini
     [servers]
     s-01 ansible_host=172.16.255.1
     ```

2. **Playbooks:**
   - Located in `ansible/playbooks/`, playbooks manage hardware-specific tasks.

3. **Hardware Profile Files:**
   - Store configuration per host, like `profile1.yml`:
     ```yaml
     hardware_settings:
       - src: templates/config.j2
         dest: /etc/app/config
     ```

### Snowfall Lib and Nixcicle
- **System Configurations:**
  Organized under `systems/`:
  ```
  systems/
    x86_64-linux/
      <machine>/
        boot-decryption.nix
        default.nix
        disks.nix
  ```

- **Shared Modules:**
  Located in `luxnix/modules/`.

---

## Common Tasks and Commands

### Updating Hostnames
After initialization, rename your machine in `/etc/nixos/configuration.nix`:
```nix
networking.hostName = "LuxNixMachineName (e.g. gc-01)";
```
Apply changes:
```bash
sudo nixos-rebuild switch
```

### Updating Home Environment
Shortcut:
```bash
nhh
```
Fallback:
```bash
nh home switch
```

---

## System Maintenance

### Nix Garbage Collection
Shortcut:
```bash
cleanup
cleanup-roots
```
Fallback:
```bash
sudo nix-collect-garbage -d
sudo nix-store --gc
```
After cleanup:
```bash
sudo nix-store --verify --check-contents --repair
```

### Removing Old Generations
```bash
sudo rm /nix/var/nix/gcroots/auto/*
```


## Boot Decryption Setup

The boot decryption setup involves:

1. Creating a USB decryption stick:
   ```bash
   sudo boot-decryption-stick-setup
   ```

2. Importing the configuration:
   ```nix
   {
     imports = [
       ./hardware-configuration.nix
       ./disks.nix
       ./boot-decryption-config.nix
     ];
   }
   ```

See [Boot Decryption Documentation](security.md#boot-decryption-usb-stick-setup) for detailed setup instructions.

## Hardware Detection

LuxNix uses various methods for hardware detection:

1. NixOS Hardware Modules:
   ```nix
   # In flake.nix
   inputs.nixos-hardware.url = "github:nixos/nixos-hardware";
   ```

2. Automatic hardware detection during installation

3. Manual configuration when needed

## Required Information

To complete hardware setup, you'll need:

1. Storage Device Information:
   - Device paths (e.g., `/dev/nvme0n1`)
   - Partition layout
   - LUKS encryption details ([see security guide](security.md#luks-encryption-management))

2. Hardware Specifics:
   - CPU type (Intel/AMD)
   - GPU details
   - Special hardware features

3. Boot Requirements:
   - UEFI/Legacy boot
   - Secure Boot status
   - TPM availability

## Next Steps

After hardware setup:
1. Complete [security configuration](security.md)
2. Set up user environment
3. Configure system services

## Troubleshooting

Common issues and solutions:
1. Boot failures: Check boot decryption stick configuration
2. Hardware detection issues: Update hardware-configuration.nix
3. Disk mounting problems: Verify disks.nix configuration
