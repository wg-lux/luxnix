
#  🟦 LuxNix - Professional NixOS Configuration Framework

A comprehensive NixOS configuration framework designed for research and development environments, emphasizing security, reproducibility, and automated deployment. Built using Snowfall Lib and Nixicle, this architecture easily manages multiple systems and user environments with a focus on enabling fast GPU computing and secure networking.

It provides a securely encrypted setup for study laptops, enabling research on protected data. 
This enables cooperation among research centers.

This infrastructure was built in the context of the ColoReg study. Here the main use case will be gathering medical study data.

## 🔎 Overview 


### [Table Of Contents - automatically generated](https://github.com/wg-lux/luxnix/wiki)
### [Shortcuts For Easy LuxNix Usage](https://github.com/wg-lux/luxnix/wiki/LX-Cheatsheet)
### [Common Errors In LuxNix](https://github.com/wg-lux/luxnix/wiki/Common-Errors)
### [Prerequisites](https://github.com/wg-lux/luxnix/wiki/Hardware-Setup#hardware-setup)
- NixOS installation media
- UEFI-capable system
- Storage device (NVMe or SATA)
- USB drive for boot decryption (optional)
- FIDO2 security key (optional)
### [Example Of Deploying LuxNix: Deployment Guide](https://github.com/wg-lux/luxnix/wiki/Deployment-Guide#Deployment)
### [LUKS Secrets Management](https://github.com/wg-lux/luxnix/wiki/Security#luks-encryption-management)
### [Boot Decryption & USB Stick Setup](https://github.com/wg-lux/luxnix/wiki/Security#boot-decryption-usb-stick-setup)
### [Service Management](https://github.com/wg-lux/luxnix/wiki/Service-Architecture#overview)
### [Access Management](https://github.com/wg-lux/luxnix/wiki/Access-Management#access-control)
### [Tools For Development](https://github.com/wg-lux/luxnix/wiki/Development#development)

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
2. Follow the [deployment guide in the Wiki](https://github.com/wg-lux/luxnix/wiki/Deployment-Guide)
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

Comprehensive documentation is available in the **[Luxnix Wiki](https://github.com/wg-lux/luxnix/wiki)**:
- [Deployment Guide](https://github.com/wg-lux/luxnix/wiki/Deployment-Guide)
- [Network Architecture](https://github.com/wg-lux/luxnix/wiki/Network-Architecture)
- [Service Configuration](https://github.com/wg-lux/luxnix/wiki/Service-Architecture)
- [Hardware Setup](https://github.com/wg-lux/luxnix/wiki/Hardware-Setup)
- [User Management](https://github.com/wg-lux/luxnix/wiki/User-Management)

## 🛟 Support

For issues and questions:
- Create an issue in the repository
- Check the **[Luxnix Wiki](https://github.com/wg-lux/luxnix/wiki)** for documentation
- Review the **[deployment guide](https://github.com/wg-lux/luxnix/wiki/Deployment-Guide)** for common problems

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

## 📚 Documentation Wiki

The following documents have been moved from the repository into the **[Luxnix Wiki](https://github.com/wg-lux/luxnix/wiki)** for easier access and centralized maintenance:

### Luxnix Documentation
- [Installation Guide - NixOS and Setting Up Luxnix](https://github.com/wg-lux/luxnix/wiki/Installation-Guide---NixOS-and-Setting-Up-Luxnix)
- [Flake.nix & Garbage Collection](https://github.com/wg-lux/luxnix/wiki/Flake.nix-&-Garbage-Collection)
- [Access Management](https://github.com/wg-lux/luxnix/wiki/Access-Management)
- [Roles](https://github.com/wg-lux/luxnix/wiki/Roles)
- [LX Cheatsheet](https://github.com/wg-lux/luxnix/wiki/LX-Cheatsheet)
- [tmux CLI Cheatsheet](https://github.com/wg-lux/luxnix/wiki/tmux-CLI-Cheatsheet)
- [Deployment Guide](https://github.com/wg-lux/luxnix/wiki/Deployment-Guide)
- [Development](https://github.com/wg-lux/luxnix/wiki/Development)
- [Hardware Setup](https://github.com/wg-lux/luxnix/wiki/Hardware-Setup)
- [Network Architecture](https://github.com/wg-lux/luxnix/wiki/Network-Architecture)
- [Security Improvements](https://github.com/wg-lux/luxnix/wiki/Security-Improvements)
- [Security](https://github.com/wg-lux/luxnix/wiki/Security)
- [Service Architecture](https://github.com/wg-lux/luxnix/wiki/Service-Architecture)
- [User Management](https://github.com/wg-lux/luxnix/wiki/User-Management)
- [Systemd tmpfiles Rules in NixOS](https://github.com/wg-lux/luxnix/wiki/Systemd-tmpfiles-Rules-in-NixOS)
- [Common Errors](https://github.com/wg-lux/luxnix/wiki/Common-Errors)
- [NixOs Configuration Testing with Eval](https://github.com/wg-lux/luxnix/wiki/NixOs-Configuration-Testing-with-Eval)
- [System Language Change](https://github.com/wg-lux/luxnix/wiki/System-Language-Change)
- [Roles Documentation](https://github.com/wg-lux/luxnix/wiki/Roles-Documentation)
- [Doc Maintenance Schedule](https://github.com/wg-lux/luxnix/wiki/Doc-Maintenance-Schedule)
- [Luxnix Server Setup with example](https://github.com/wg-lux/luxnix/wiki/Luxnix-Server-Setup-with-example)

### Database Documentation
- [Postgres Config Guide](https://github.com/wg-lux/luxnix/wiki/Postgres-Config-Guide)
- [Postgres Documentation](https://github.com/wg-lux/luxnix/wiki/Postgres-Documentation)
- [Postgres gc-10 Declarative Setup Summary](https://github.com/wg-lux/luxnix/wiki/Postgres-gc-10-Declarative-Setup-Summary)
- [Endoreg Central Architecture](https://github.com/wg-lux/luxnix/wiki/Endoreg-Central-Architecture)

### Ansible
- [Readme](https://github.com/wg-lux/luxnix/wiki/Readme)
- [Ansible CMDB Readme](https://github.com/wg-lux/luxnix/wiki/Ansible-CMDB-Readme)
- [Process flow of creating Hosts, Roles, Groups](https://github.com/wg-lux/luxnix/wiki/Process-flow-of-creating-Hosts,-Roles,-Groups)
- [Adding a New User Configuration](https://github.com/wg-lux/luxnix/wiki/Adding-a-New-User-Configuration)
- [Maintenance & Security: Auto Update #6](https://github.com/wg-lux/luxnix/wiki/Maintenance-&-Security:-Auto-Update-%236)
- [Home Configuration Autoconf Flow (Step-by-Step)](https://github.com/wg-lux/luxnix/wiki/Home-Configuration-Autoconf-Flow-%28Step-by-Step%29)
- [Guide to Define New Setting With Example](https://github.com/wg-lux/luxnix/wiki/Guide-to-Define-New-Setting-With-Example)
- [Autoconfig- create inventory.yml using Python Script](https://github.com/wg-lux/luxnix/wiki/Autoconfig--create-inventory.yml-using-Python-Script)
- [Updated : Generating home config files using autoconfig](https://github.com/wg-lux/luxnix/wiki/Updated-:-Generating-home-config-files-using-autoconfig)

### Devlog
- [git](https://github.com/wg-lux/luxnix/wiki/git)
- [vscode](https://github.com/wg-lux/luxnix/wiki/vscode)
- [fix_long_lines](https://github.com/wg-lux/luxnix/wiki/fix_long_lines)
- [kernel](https://github.com/wg-lux/luxnix/wiki/kernel)
- [keycloak-setup](https://github.com/wg-lux/luxnix/wiki/keycloak-setup)
- [network](https://github.com/wg-lux/luxnix/wiki/network)
- [setup-mail](https://github.com/wg-lux/luxnix/wiki/setup-mail)
- [setup-s04](https://github.com/wg-lux/luxnix/wiki/setup-s04)
- [syncthing](https://github.com/wg-lux/luxnix/wiki/syncthing)
- [2025-01-29 - postgres](https://github.com/wg-lux/luxnix/wiki/2025-01-29---postgres)


### Figures
- [Diagram for Luxnix](https://github.com/wg-lux/luxnix/wiki/Diagram-for-Luxnix)
- [Cloudflare-traefik](https://github.com/wg-lux/luxnix/wiki/Cloudflare-traefik)
- [Forward Auth Sonarr](https://github.com/wg-lux/luxnix/wiki/Forward-Auth-Sonarr)
- [HTTP Basic Auth](https://github.com/wg-lux/luxnix/wiki/HTTP-Basic-Auth)
- [tls-cloudflare-issue](https://github.com/wg-lux/luxnix/wiki/tls-cloudflare-issue)
- [Tunnel Order](https://github.com/wg-lux/luxnix/wiki/Tunnel-Order)
- [update-outpost](https://github.com/wg-lux/luxnix/wiki/update-outpost)

### Miscellaneous
- [Style Guide](https://github.com/wg-lux/luxnix/wiki/Style-Guide)




## 📜 License

MIT - see LICENSE
---

Built with ❄️ using NixOS
