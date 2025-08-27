# Luxnix Virtualization Module

This module provides comprehensive virtualization support for Luxnix systems, including containerization with Podman, KVM/QEMU virtual machines, and GPU passthrough capabilities with VFIO.

## Overview

The virtualization module supports three main virtualization technologies:

1. **Podman Containerization** - Docker-compatible container runtime
2. **KVM/QEMU Virtualization** - Full virtual machine support with libvirtd
3. **VFIO GPU Passthrough** - Hardware acceleration for virtual machines

## Quick Start

Enable basic virtualization support:

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    
    # Enable Podman (default: enabled)
    podman.enable = true;
    
    # Enable KVM for virtual machines
    kvm.enable = true;
    
    # Optional: Enable GPU passthrough
    vfio.enable = false;
  };
}
```

## Configuration Options

### Podman Configuration

Podman provides Docker-compatible containerization with rootless operation by default.

```nix
luxnix.generic-settings.virtualization.podman = {
  enable = true;                    # Enable Podman (default: true)
  dockerCompat = true;             # Docker CLI compatibility (default: true)
  socketEnable = true;             # Docker socket compatibility (default: true)
  dnsEnabled = true;               # DNS for default network (default: true)
  
  extraConfig = {                  # Additional Podman configuration
    # Custom registry configuration, etc.
  };
};
```

**Features:**
- Docker CLI compatibility layer
- Docker socket API compatibility
- Rootless container execution
- DNS resolution for containers
- Network isolation and management

### KVM/QEMU Configuration

Full virtual machine support with libvirtd management.

```nix
luxnix.generic-settings.virtualization.kvm = {
  enable = true;
  
  # Additional packages (defaults shown)
  packages = with pkgs; [
    libguestfs      # Guest filesystem tools
    win-virtio      # Windows VirtIO drivers
    win-spice       # Windows SPICE drivers
    virt-manager    # Graphical VM management
    virt-viewer     # VM console viewer
  ];
  
  libvirtd = {
    allowedBridges = ["nm-bridge" "virbr0"];  # Network bridges
    onBoot = "ignore";                        # VM startup behavior: "start" | "ignore"
    onShutdown = "shutdown";                  # VM shutdown behavior: "shutdown" | "destroy"
    clearEmulationCapabilities = true;       # Security setting
  };
  
  deviceACL = [
    "/dev/null" "/dev/full" "/dev/zero"
    "/dev/random" "/dev/urandom"
    "/dev/ptmx" "/dev/kvm"
  ];
  
  qemu = {
    swtpm = true;          # Software TPM support
    ovmf = true;           # UEFI firmware support
    runAsRoot = false;     # Run QEMU as unprivileged user
  };
  
  spiceUSBRedirection = true;  # USB device passthrough via SPICE
  kvmgt = false;              # Intel GVT-g GPU virtualization
};
```

**Features:**
- Full hardware virtualization with KVM
- QEMU machine emulation
- libvirtd service management
- SPICE protocol for remote display
- UEFI/OVMF firmware support
- Software TPM (vTPM) support
- USB device redirection
- Network bridge management

### VFIO GPU Passthrough

Advanced GPU passthrough for high-performance virtual machines.

```nix
luxnix.generic-settings.virtualization.vfio = {
  enable = true;
  
  IOMMUType = "intel";                    # "intel" or "amd"
  devices = ["10de:1b80" "10de:10f0"];   # PCI device IDs to passthrough
  
  # Boot options
  disableEFIfb = false;      # Disable EFI framebuffer
  blacklistNvidia = false;   # Blacklist Nvidia drivers
  ignoreMSRs = false;        # Ignore model-specific registers
  
  # Hugepages for better performance
  hugepages = {
    enable = true;
    defaultPageSize = "1G";   # "1M", "2M", "1G"
    pageSize = "1G";
    numPages = 8;             # 8GB of hugepages
  };
  
  # Looking Glass for seamless GPU sharing
  lookingGlass = {
    enable = true;
    sharedMemorySize = "128M";
  };
  
  # Custom shared memory files
  sharedMemoryFiles = {
    "my-app" = {
      user = "admin";
      group = "kvm";
      mode = "0660";
    };
  };
};
```

**Features:**
- Direct GPU hardware passthrough
- Intel VT-d / AMD-Vi IOMMU support
- Hugepages for improved performance
- Looking Glass for seamless desktop integration
- Custom shared memory file management
- Automatic VFIO driver binding

### Global Settings

```nix
luxnix.generic-settings.virtualization = {
  # Additional architecture emulation
  supportedArchitectures = ["aarch64-linux"];
  
  # User groups for virtualization access
  userGroups = ["libvirtd" "kvm" "docker"];
};
```

## Hardware Requirements

### KVM Requirements
- CPU with hardware virtualization support (Intel VT-x or AMD-V)
- Sufficient RAM for host and guests
- Storage space for virtual machine images

### VFIO Requirements
- CPU and motherboard with IOMMU support
- Multiple GPUs or integrated graphics + discrete GPU
- UEFI firmware (for OVMF support)
- IOMMU groups properly separated

## Security Considerations

The module implements several security measures:

1. **User Permissions**: Admin user is added to appropriate groups (`libvirtd`, `kvm`)
2. **Sensitive Services**: Virtualization services are added to the sensitive service group
3. **Device ACL**: Controlled access to hardware devices
4. **Unprivileged QEMU**: QEMU runs as dedicated user (not root)
5. **Network Isolation**: Proper network bridging and isolation

## Troubleshooting

### Common Issues

**KVM not working:**
```bash
# Check if KVM is available
lsmod | grep kvm

# Check QEMU capabilities
qemu-system-x86_64 -accel help
```

**VFIO passthrough issues:**
```bash
# Check IOMMU groups
find /sys/kernel/iommu_groups/ -type l

# Verify VFIO driver binding
lspci -nnk | grep -A2 "VGA\|3D"
```

**Permission issues:**
```bash
# Check user groups
groups $USER

# Verify libvirtd access
virsh list --all
```

### Performance Tuning

For optimal performance:

1. **Enable hugepages** for memory-intensive workloads
2. **Use virtio drivers** in guest systems
3. **Configure CPU pinning** for dedicated cores
4. **Enable nested virtualization** if needed

## Integration with Luxnix

This module integrates with other Luxnix components:

- **Generic Settings**: Uses sensitive service group configuration
- **User Management**: Automatically configures admin user permissions  
- **Network**: Works with existing network bridge configurations
- **Security**: Follows Luxnix security patterns and group management

## Examples

### Basic Development Setup
```nix
luxnix.generic-settings.virtualization = {
  enable = true;
  podman.enable = true;
  kvm.enable = true;
};
```

### Gaming with GPU Passthrough
```nix
luxnix.generic-settings.virtualization = {
  enable = true;
  kvm.enable = true;
  vfio = {
    enable = true;
    IOMMUType = "intel";
    devices = ["10de:1b80"];  # Your GPU device ID
    hugepages = {
      enable = true;
      pageSize = "1G";
      numPages = 8;
    };
    lookingGlass.enable = true;
  };
};
```

### Container-Only Setup
```nix
luxnix.generic-settings.virtualization = {
  enable = true;
  podman = {
    enable = true;
    dockerCompat = true;
  };
  kvm.enable = false;
  vfio.enable = false;
};
```

## See Also

- [NixOS Virtualization Documentation](https://nixos.org/manual/nixos/stable/index.html#ch-virtualisation)
- [Podman Documentation](https://docs.podman.io/)
- [QEMU Documentation](https://www.qemu.org/documentation/)
- [VFIO GPU Passthrough Guide](https://wiki.archlinux.org/title/PCI_passthrough_via_OVMF)
