# LuxNix Virtualization Configuration Guide

## Overview

The LuxNix virtualization system provides unified configuration for containerization and virtual machine technologies through the `luxnix.generic-settings.virtualization` module. This system supports:

- **Podman** - Container runtime with Docker compatibility
- **KVM/QEMU** - Full system virtualization
- **VFIO** - GPU passthrough for VMs
- **Looking Glass** - Low-latency VM display

## Prerequisites, validation, and recovery

Before enabling KVM or VFIO, confirm that the host hardware supports the
selected IOMMU mode, record the GPU and audio PCI IDs, ensure console or
out-of-band access is available, and keep a known-good NixOS generation. Do
not apply GPU passthrough settings to a host whose display or remote access
depends on that GPU without a recovery path.

After changing virtualization settings, evaluate and build the host, activate
the reviewed generation, and verify `systemctl is-active libvirtd`, access to
`/dev/kvm`, the intended device driver bindings, and a disposable VM or
container. For VFIO, also verify that the host display and SSH access remain
available.

If activation, host access, or a VM fails, stop the affected VM, use console or
out-of-band access, and boot or switch to the previous NixOS generation (for
example `sudo nixos-rebuild switch --rollback`). Restore the prior PCI IDs and
IOMMU/VFIO settings in the canonical host configuration, regenerate, and
repeat validation. Do not detach a production GPU or delete VM storage while
diagnosing a failed change.

## Configuration Structure

All virtualization options are configured under `luxnix.generic-settings.virtualization` in your system configuration.

## Basic Usage

### Enable Virtualization

To enable virtualization support, add this to your system configuration:

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
  };
}
```

This enables Podman by default with Docker compatibility.

## Podman Configuration

### Basic Podman Setup

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    podman = {
      enable = true;                    # Default: true
      dockerCompat = true;              # Default: true
      socketEnable = true;              # Default: true
      dnsEnabled = true;                # Default: true
    };
  };
}
```

### Advanced Podman Configuration

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    podman = {
      enable = true;
      extraConfig = {
        # Additional Podman network settings
        subnet = "10.89.0.0/24";
        gateway = "10.89.0.1";
      };
    };
  };
}
```

## KVM Virtualization

### Basic KVM Setup

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    kvm = {
      enable = true;
      spiceUSBRedirection = true;       # Default: true
      kvmgt = false;                    # Intel GVT-g, Default: false
    };
  };
}
```

### Advanced KVM Configuration

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    kvm = {
      enable = true;
      
      # Custom package selection
      packages = with pkgs; [
        libguestfs
        win-virtio
        win-spice
        virt-manager
        virt-viewer
        # Add custom virtualization tools
      ];
      
      # LibVirtD configuration
      libvirtd = {
        allowedBridges = [ "nm-bridge" "virbr0" "br0" ];
        onBoot = "ignore";              # or "start"
        onShutdown = "shutdown";        # or "destroy"
        clearEmulationCapabilities = true;
      };
      
      # Device Access Control List
      deviceACL = [
        "/dev/null" "/dev/full" "/dev/zero"
        "/dev/random" "/dev/urandom"
        "/dev/ptmx" "/dev/kvm"
        "/dev/input/by-id/usb-*"       # USB devices
      ];
      
      # QEMU settings
      qemu = {
        swtpm = true;                   # Software TPM
        ovmf = true;                    # UEFI support
        runAsRoot = false;              # Security: run as qemu user
      };
    };
  };
}
```

## VFIO GPU Passthrough

### Basic VFIO Setup

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    kvm.enable = true;                  # Required for VFIO
    vfio = {
      enable = true;
      IOMMUType = "intel";              # or "amd"
      devices = [
        "10de:1b80"                     # GPU PCI ID
        "10de:10f0"                     # GPU Audio PCI ID
      ];
    };
  };
}
```

### Advanced VFIO Configuration

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    kvm.enable = true;
    vfio = {
      enable = true;
      IOMMUType = "intel";
      devices = [ "10de:1b80" "10de:10f0" ];
      
      # Advanced options
      disableEFIfb = true;              # Disable EFI framebuffer
      blacklistNvidia = true;           # Blacklist host GPU drivers
      ignoreMSRs = true;                # For some Windows VMs
      
      # Hugepages for performance
      hugepages = {
        enable = true;
        defaultPageSize = "1G";
        pageSize = "1G";
        numPages = 8;                   # 8GB of hugepages
      };
      
      # Looking Glass setup
      lookingGlass = {
        enable = true;
      };
      
      # Custom shared memory files
      sharedMemoryFiles = {
        "looking-glass" = {
          user = "admin";
          group = "kvm";
          mode = "0660";
        };
      };
    };
  };
}
```

## Multi-Architecture Support

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    supportedArchitectures = [
      "aarch64-linux"                  # ARM64 emulation
      "i686-linux"                     # 32-bit x86 emulation
    ];
  };
}
```

## User Access Configuration

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    kvm.enable = true;
    
    # Groups to add admin user to
    userGroups = [
      "libvirtd"                       # LibVirt management
      "kvm"                           # KVM access
      "docker"                        # Docker socket (if using Podman compat)
    ];
  };
}
```

## Common Configuration Examples

### Development Environment

Perfect for software development with containers:

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    podman = {
      enable = true;
      dockerCompat = true;
      socketEnable = true;
    };
    # KVM disabled by default - containers only
  };
}
```

### Virtualization Host

For running VMs alongside containers:

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    podman.enable = true;
    kvm = {
      enable = true;
      spiceUSBRedirection = true;
      qemu = {
        swtpm = true;
        ovmf = true;
      };
    };
    supportedArchitectures = [ "aarch64-linux" ];
  };
}
```

### Gaming/VFIO Host

For GPU passthrough gaming setups:

```nix
{
  luxnix.generic-settings.virtualization = {
    enable = true;
    kvm.enable = true;
    vfio = {
      enable = true;
      IOMMUType = "intel";              # or "amd"
      devices = [ "10de:1b80" "10de:10f0" ];  # Replace with your GPU IDs
      blacklistNvidia = true;
      hugepages = {
        enable = true;
        defaultPageSize = "1G";
        pageSize = "1G";
        numPages = 16;
      };
      lookingGlass.enable = true;
    };
  };
}
```

## Finding GPU PCI IDs

To find your GPU's PCI ID for VFIO configuration:

```bash
# List all PCI devices
lspci -nn

# Find GPU specifically
lspci -nn | grep -i nvidia
# or for AMD
lspci -nn | grep -i amd

# Example output:
# 01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GP104 [GeForce GTX 1070] [10de:1b81]
# 01:00.1 Audio device [0403]: NVIDIA Corporation GP104 High Definition Audio Controller [10de:10f0]

# Use the IDs in brackets: 10de:1b81, 10de:10f0
```

## Validation and Debugging

### Check Configuration

After applying your configuration, verify the services are running:

```bash
# Check Podman
systemctl status podman.service
podman info

# Check LibVirt (if KVM enabled)
systemctl status libvirtd.service
virsh list --all

# Check VFIO devices (if VFIO enabled)
ls /dev/vfio/
dmesg | grep -i vfio
```

### Common Issues

1. **VFIO not binding devices**: Check IOMMU is enabled in BIOS
2. **Permission denied**: Ensure user is in correct groups (libvirtd, kvm)
3. **Podman socket issues**: Restart podman.service
4. **VM performance**: Enable hugepages for better performance

## Security Considerations

- VFIO requires elevated privileges - only enable on trusted systems
- Consider running QEMU as non-root user (default in this configuration)
- Use TPM support for Windows 11 VMs
- Regularly update virtualization packages for security fixes

## Performance Tuning

### For VMs
- Enable hugepages for memory-intensive VMs
- Pin CPU cores to VMs for consistent performance
- Use virtio drivers for better I/O performance
- Consider SR-IOV for network passthrough

### For Containers
- Use bind mounts instead of volumes for better performance
- Configure appropriate resource limits
- Use multi-stage builds to reduce image size

## Integration with LuxNix Roles

The virtualization configuration integrates with other LuxNix components:

- Automatically adds users to sensitive service groups
- Respects system security settings
- Integrates with the secrets management system
- Works with the networking configuration

This modular approach allows you to enable only the virtualization features you need while maintaining system security and performance.
