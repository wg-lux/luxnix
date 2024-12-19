# Security Documentation

This document outlines the security measures and encryption setup for LuxNix, with a focus on LUKS encryption and key management.

## Overview

LuxNix implements robust security measures using LUKS (Linux Unified Key Setup) standard encryption for protecting sensitive data, including:
- SSH keys
- Passwords
- Usernames
- System configurations

## LUKS Encryption Management

### Viewing Keyslot Information

To explore registered keyfiles and manage LUKS-encrypted devices, use the `cryptsetup` tool. Here's how to view and manage encryption keys:

```bash
# View all keyslots for a LUKS device
sudo cryptsetup luksDump /dev/sdX
```

The output will display detailed LUKS header information:

```
LUKS header information for /dev/sdX
Version: 2
Epoch: 1
Keyslots:
 0: ENABLED
    Key Size: 512 bits
    Priority: normal
 1: DISABLED
 2: DISABLED
 3: ENABLED
    Key Size: 512 bits
    Priority: high
```

**Note**: 
- ENABLED keyslots contain active, valid keys or keyfiles
- DISABLED keyslots are inactive and contain no valid keys

### Managing Keyfiles and Keyslots

#### Removing Keyfiles

1. Remove a specific keyfile:
```bash
sudo cryptsetup luksRemoveKey /dev/sdX --key-file /path/to/old-keyfile
```

2. Remove a passphrase (interactive):
```bash
sudo cryptsetup luksRemoveKey /dev/sdX
```

3. Remove a specific keyslot by number:
```bash
sudo cryptsetup luksKillSlot /dev/sdX N
```

### Example Usage

```bash
# List all keyslots on NVMe drive
sudo cryptsetup luksDump /dev/nvme0n1p1

# Remove old keyfile from keyslot 1
sudo cryptsetup luksRemoveKey /dev/nvme0n1p1 --key-file /etc/keys/old-keyfile

# Remove keyslot 2 directly
sudo cryptsetup luksKillSlot /dev/nvme0n1p1 2
```

## Boot Decryption USB Stick Setup

LuxNix includes a dedicated module for creating and managing boot decryption USB sticks.

### Module Location
```
modules/nixos/luxnix/boot-decryption-stick
```

### Setup Instructions

1. Run the setup script as root:
```bash
sudo boot-decryption-stick-setup
```

2. The script generates a Nix configuration file at:
```
systems/x86_64-linux/${hostname}/boot-decryption-config.nix
```

3. Import the configuration in your system configuration file. Example (`gc-06/default.nix`):

```nix
{
  pkgs,
  lib,
  ...
}@inputs:
let
  sensitiveHdd = import ./sensitive-hdd.nix {};
  extraImports = [
    ./boot-decryption-config.nix
  ];
in
{
  imports = [
    ./hardware-configuration.nix
    ./disks.nix
  ] ++ extraImports;
  # ...
}
```

## Security Best Practices

1. Regularly audit active keyslots using `luksDump`
2. Remove unused or compromised keyfiles promptly
3. Maintain secure backups of encryption keys
4. Document all changes to encryption configuration
5. Test boot decryption USB sticks regularly

## Additional Resources

For more detailed information about LuxNix security features, refer to:
- LUKS2 Documentation
- NixOS Security Guide
- LuxNix Deployment Guide (`docs/deployment-guide.md`)