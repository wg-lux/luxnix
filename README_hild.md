
#  🟦 LuxNix - Professional NixOS Configuration Framework

A comprehensive NixOS configuration framework designed for research and development environments, emphasizing security, reproducibility, and automated deployment. Built using Snowfall Lib and Nixicle, this architecture easily manages multiple systems and user environments with a focus on enabling fast GPU computing and secure networking.

It provides a securely encrypted setup for study laptops, enabling research on protected data. 
This enables cooperation among research centers.

This infrastructure was built in the context of the ColoReg study. Here the main use case will be gathering medical study data.

## 🔎 Overview 


### [Table Of Contents - automatically generated](TABLE_OF_CONTENTS.md)
### [Prerequisites](hardware-setup.md#hardware-setup)
- NixOS installation media
- UEFI-capable system
- Storage device (NVMe or SATA)
- USB drive for boot decryption (optional)
- FIDO2 security key (optional)
### [Example Of Deploying LuxNix: Deployment Guide](docs/deployment-guide.md#Deployment)
### [LUKS Secrets Management](security.md#luks-encryption-management)
### [Boot Decryption & USB Stick Setup](security.md#boot-decryption-usb-stick-setup)
### [Service Management](service-architecture.md#overview)
### [Access Management](access-management.md#access-control)
### [Tools For Development](development.md#development)

## 🛠️ Initial Setup
1. Verify UEFI boot mode
2. Prepare storage devices
3. Set up LUKS encryption
4. Follow hardware setup guide

### References for the NixOS Setup used:

- Nixicle https://github.com/hmajid2301/nixicle
- Snowflakes OS Quickstart https://snowfall.org/guides/lib/quickstart/

## 🚀 Key Features

### System Architecture
- **Modular Design**: Built on Snowfall Lib for clean separation of concerns and maintainable code
- **Multi-System Support**: Manages configurations for development workstations (gc-*) and servers (s-*)
- **Role-Based Configuration**: Predefined roles for common use cases:
  - GPU Development Environment
  - Base Server Configuration
  - Monitoring Systems
  - Desktop Environment (KDE Plasma)

### Security & Hardware
- **Disk Encryption**: LUKS2 encryption with FIDO2 support
- **Impermanence**: Stateless system design with persistent data management
- **Hardware Optimization**:
  - NVIDIA Prime support for hybrid graphics
  - Custom hardware configurations for different machine types
  - Advanced audio and bluetooth management

### Development Environment
- **GPU Computing**: Configured for research and development workloads
- **Development Tools**:
  - Container support (Podman)
  - Language-specific toolchains
  - CLI utilities (modern-unix tools)
- **Terminal Environment**:
  - Multiple terminal emulator options (Alacritty, Foot, Kitty, WezTerm)
  - ZSH configuration with modern tools

### Infrastructure Services
- **Authentication**: Authentik for centralized identity management
- **Storage**: MinIO for S3-compatible object storage
- **Monitoring**: Comprehensive monitoring setup with Netdata
- **Network**: Advanced VPN configuration and Traefik for service routing

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
git clone https://github.com/your-username/luxnix.git

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

## 🖥️ Supported Systems

- Development Workstations (gc-*)
  - Hybrid GPU configurations
  - Development toolchains
  - Desktop environments

- Servers (s-*)
  - Infrastructure services
  - Monitoring systems
  - Network services

## 📚 Documentation

Detailed documentation is available in the `docs/` directory:
- Deployment Guide
- Network Architecture
- Service Configuration
- Hardware Setup

## 🛟 Support

For issues and questions:
- Create an issue in the repository
- Check the documentation in `docs/`
- Review the deployment guide for common problems

## 📜 License

MIT - see LICENSE
---

Built with ❄️ using NixOS
