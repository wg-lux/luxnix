
#  🟦 LuxNix - Professional NixOS Configuration Framework

A comprehensive NixOS configuration framework designed for research and development environments, emphasizing security, reproducibility, and automated deployment. Built using Snowfall Lib and Nixicle, this architecture easily manages multiple systems and user environments with a focus on enabling fast GPU computing and secure networking.

It provides a securely encrypted setup for study laptops, enabling research on protected data. 
This enables cooperation among research centers.

This infrastructure was built in the context of the ColoReg study. Here the main use case will be gathering medical study data.

## 🔎 Overview 


### [Table Of Contents - automatically generated](TABLE_OF_CONTENTS.md)
### [Shortcuts For Easy LuxNix Usage](LxCheatsheet.md)
### [Common Errors In LuxNix](CommonErrors.md)
### [Prerequisites](docs/hardware-setup.md#hardware-setup)
- NixOS installation media
- UEFI-capable system
- Storage device (NVMe or SATA)
- USB drive for boot decryption (optional)
- FIDO2 security key (optional)
### [Example Of Deploying LuxNix: Deployment Guide](docs/deployment-guide.md#Deployment)
### [LUKS Secrets Management](docs/security.md#luks-encryption-management)
### [Boot Decryption & USB Stick Setup](docs/security.md#boot-decryption-usb-stick-setup)
### [Service Management](docs/service-architecture.md#overview)
### [Access Management](docs/access-management.md#access-control)
### [Tools For Development](docs/development.md#development)

## 🛠️ Initial Setup
1. Verify UEFI boot mode
2. Prepare storage devices
3. Set up LUKS encryption
4. Follow hardware setup guide

### References for the NixOS Setup used:

- Nixicle https://github.com/hmajid2301/nixicle
- Snowflakes OS Quickstart https://snowfall.org/guides/lib/quickstart/

## 🛠 Getting Started

### Prerequisites
- NixOS installation media
- Basic understanding of Nix flakes
- Hardware compatible with NixOS

### Quick Start
1. Boot from NixOS installation media
2. Follow the deployment guide in `docs/deployment-guide.md`
3. Choose appropriate system configuration from `systems/x86_64-linux/`

### Deployment
```bash
# Clone the repository
git clone https://github.com/wg-lux/luxnix.git

# Deploy to a new system
nixos-anywhere --flake '.#hostname' nixos@ip-address

# Update existing system
nh os switch
nho #shortcut
```

## 📁 Repository Structure

```
luxnix/
├── flake.nix           # Main flake configuration
├── modules/            # Modular system configurations
│   ├── home/          # Home-manager configurations
│   └── nixos/         # System-level configurations
├── systems/           # Per-machine configurations
└── homes/            # User-specific configurations
```

## 🔒 Security Features

- LUKS2 encryption with FIDO2 device support
- Secure boot configuration (optional)
- VPN integration for secure networking
- Role-based access control
- Secrets management with SOPS

## 🖥️ Supported System Types

- Development Workstations (gc-*)
  - Hybrid GPU configurations
  - Development toolchain preinstalled
  - Desktop environment with KDE and Plasma on Linux (NixOS Distro)

- Servers (s-*)
  - Infrastructure to outsource computation
  - Monitoring systems
  - Network services

## 📚 Documentation

Detailed documentation is available in the `docs/` directory:
- Deployment Guide
- Network Architecture
- Service Configuration
- Hardware Setup
- User Management

## 🛟 Support

For issues and questions:
- Create an issue in the repository
- Check the documentation in `docs/`
- Review the deployment guide for common problems

## Keycloak and Nextcloud login
Make sure account has been created.

## Step 1: Access Keycloak

Please visit the following link:  
 [https://keycloak.endo-reg.net/](https://keycloak.endo-reg.net/)  
Use the provided credentials to log in.

## Step 2: Complete Required Actions

After logging in, you will be automatically guided through the following steps:

-  Verify your email address  
-  Set up OTP (two-factor authentication)  
-  Change your password  

Make sure to complete all steps.

## Step 3: Log In to Nextcloud

Once all steps are completed, go to:  
 [https://cloud.endo-reg.net/login](https://cloud.endo-reg.net/login)

Click **"Login with Keycloak"**.

You can now use your **Keycloak credentials** to access **Nextcloud**.

## Ste 4: Log In to Nextcloud Mobile Application
Download the mobile app.
Use this link: https://cloud.endo-reg.net
Enter credential/login using keyscloak


## 📜 License

MIT - see LICENSE
---

Built with ❄️ using NixOS
