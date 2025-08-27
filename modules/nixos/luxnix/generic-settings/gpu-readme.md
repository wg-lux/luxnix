# Luxnix Automatic GPU Configuration

This document explains how Luxnix can automatically detect and configure AMD, Intel, and Nvidia GPUs using the integrated GPU settings in the generic-settings module.

## Overview

Luxnix provides automatic GPU configuration through the `luxnix.generic-settings.gpu` options. This system can:

1. **Automatically detect GPU type** (when set to "auto")
2. **Configure appropriate drivers** for each GPU vendor
3. **Handle hybrid graphics** (PRIME) setups
4. **Integrate with virtualization** for GPU passthrough scenarios

## Quick Start

### Basic GPU Configuration

```nix
{
  luxnix.generic-settings = {
    enable = true;
    
    gpu = {
      autoDetect = true;        # Enable automatic GPU detection
      type = "auto";            # Auto-detect GPU type
      
      # Nvidia configuration (if detected)
      nvidia = {
        enable = true;
        driver = "beta";        # "stable", "beta", or "production"
      };
      
      # AMD configuration (if detected)
      amd = {
        enable = true;
        openSource = true;      # Use open-source drivers
      };
      
      # Intel configuration (if detected)
      intel = {
        enable = true;
        vaapi = true;          # Enable hardware acceleration
      };
    };
  };
}
```

## Configuration Options

### Global GPU Settings

```nix
luxnix.generic-settings.gpu = {
  autoDetect = true;              # Enable automatic GPU detection
  type = "auto";                  # "nvidia" | "amd" | "intel" | "none" | "auto"
};
```

**GPU Type Options:**
- `"auto"` - Automatically detect GPU (recommended)
- `"nvidia"` - Force Nvidia configuration
- `"amd"` - Force AMD configuration  
- `"intel"` - Force Intel configuration
- `"none"` - Disable GPU configuration

### Nvidia Configuration

```nix
luxnix.generic-settings.gpu.nvidia = {
  enable = true;                  # Enable Nvidia support
  driver = "beta";                # Driver version: "stable", "beta", "production"
  
  # PRIME configuration for hybrid graphics
  prime = {
    enable = true;                # Enable PRIME
    nvidiaBusId = "PCI:01:00:0";  # Nvidia GPU bus ID
    onboardBusId = "PCI:00:02:0"; # Onboard GPU bus ID
    onboardType = "intel";        # "intel" or "amd"
  };
};
```

#### Finding GPU Bus IDs

To find your GPU bus IDs for PRIME configuration:

```bash
# List all PCI devices
lspci | grep -E "(VGA|3D)"

# Find specific bus IDs
lspci | grep -i nvidia
lspci | grep -i intel

# Example output:
# 00:02.0 VGA compatible controller: Intel Corporation Device
# 01:00.0 3D controller: NVIDIA Corporation Device
```

Use the format `PCI:XX:YY:Z` where XX:YY:Z corresponds to the lspci output.

### AMD Configuration

```nix
luxnix.generic-settings.gpu.amd = {
  enable = true;                  # Enable AMD support
  openSource = true;              # Use open-source drivers (AMDGPU)
};
```

**AMD Driver Options:**
- `openSource = true` - Use open-source AMDGPU drivers (recommended)
- `openSource = false` - Use proprietary AMDVLK drivers

### Intel Configuration

```nix
luxnix.generic-settings.gpu.intel = {
  enable = true;                  # Enable Intel support
  vaapi = true;                   # Enable VA-API hardware acceleration
};
```

**Intel Features:**
- Hardware video acceleration (VA-API)
- Intel Media Driver support
- Automatic integration with desktop environments

## Integration with Existing Modules

The GPU configuration automatically integrates with your existing Nvidia modules:

### With nvidia-prime module
```nix
# Old way - manual configuration
luxnix.nvidia-prime = {
  enable = true;
  nvidiaBusId = "PCI:01:00:0";
  onboardBusId = "PCI:00:02:0";
  onboardGpuType = "intel";
  nvidiaDriver = "beta";
};

# New way - automatic configuration
luxnix.generic-settings.gpu = {
  autoDetect = true;
  nvidia = {
    enable = true;
    driver = "beta";
    prime = {
      enable = true;
      nvidiaBusId = "PCI:01:00:0";
      onboardBusId = "PCI:00:02:0";
      onboardType = "intel";
    };
  };
};
```

### With nvidia-default module
```nix
# Old way
luxnix.nvidia-default = {
  enable = true;
  nvidiaDriver = "beta";
};

# New way
luxnix.generic-settings.gpu = {
  autoDetect = true;
  nvidia = {
    enable = true;
    driver = "beta";
    prime.enable = false;  # Disable PRIME for single GPU
  };
};
```

## Use Cases

### Gaming Laptop with Hybrid Graphics

```nix
{
  luxnix.generic-settings.gpu = {
    autoDetect = true;
    nvidia = {
      enable = true;
      driver = "beta";
      prime = {
        enable = true;
        nvidiaBusId = "PCI:01:00:0";      # Your dGPU
        onboardBusId = "PCI:00:02:0";     # Your iGPU  
        onboardType = "intel";
      };
    };
    intel = {
      enable = true;
      vaapi = true;
    };
  };
}
```

### AMD Desktop System

```nix
{
  luxnix.generic-settings.gpu = {
    type = "amd";                # Force AMD configuration
    amd = {
      enable = true;
      openSource = true;         # Use open-source drivers
    };
  };
}
```

### Intel-only System

```nix
{
  luxnix.generic-settings.gpu = {
    type = "intel";
    intel = {
      enable = true;
      vaapi = true;
    };
  };
}
```

### Workstation with Multiple GPUs

```nix
{
  luxnix.generic-settings.gpu = {
    autoDetect = true;
    nvidia = {
      enable = true;
      driver = "production";     # Stable drivers for workstation
      prime.enable = false;      # Single GPU mode
    };
    intel = {
      enable = true;             # For onboard graphics
      vaapi = true;
    };
  };
}
```

## Integration with Virtualization

The GPU configuration works seamlessly with the virtualization module for GPU passthrough:

```nix
{
  luxnix.generic-settings = {
    gpu = {
      nvidia = {
        enable = true;
        driver = "beta";
      };
    };
    
    virtualization = {
      enable = true;
      kvm.enable = true;
      vfio = {
        enable = true;
        IOMMUType = "intel";            # Matches CPU type
        devices = ["10de:1b80"];        # GPU PCI ID for passthrough
        blacklistNvidia = true;         # Prevent host from using GPU
      };
    };
  };
}
```

## Troubleshooting

### Common Issues

**GPU not detected:**
```bash
# Check available GPUs
lspci | grep -E "(VGA|3D)"

# Check current drivers
lsmod | grep -E "(nvidia|amdgpu|i915)"
```

**PRIME not working:**
```bash
# Check GPU status
nvidia-smi                    # For Nvidia
intel_gpu_top                 # For Intel
radeontop                     # For AMD

# Check PRIME setup
xrandr --listproviders
```

**Driver conflicts:**
- Check that only one GPU driver configuration is enabled
- Ensure proper bus IDs for PRIME setups
- Verify IOMMU settings for VFIO passthrough

### Migration from Manual Configuration

1. **Identify current GPU setup**:
   ```bash
   lspci | grep -E "(VGA|3D)"
   ```

2. **Update configuration**:
   ```nix
   # Replace manual module enables with GPU settings
   luxnix.generic-settings.gpu = {
     autoDetect = true;
     # ... configure based on your hardware
   };
   ```

3. **Test the change**:
   ```bash
   nh os build .
   nh os switch .
   ```

## Benefits

### Compared to Manual Configuration

1. **Simplified Configuration**: Single place to configure all GPU settings
2. **Automatic Integration**: Works with existing Luxnix modules
3. **Hybrid Graphics Support**: Easier PRIME configuration
4. **Consistent Interface**: Same configuration pattern for all GPU vendors
5. **Validation**: Built-in warnings for configuration conflicts
6. **Future-Proof**: Easy to extend with new GPU features

### System Integration

- **CPU Detection**: Automatically matches IOMMU type with CPU vendor
- **Virtualization**: Integrates with VFIO for GPU passthrough
- **Desktop**: Works with all supported desktop environments
- **Hardware Acceleration**: Automatic VA-API and similar setups

## Future Enhancements

Planned improvements for automatic GPU configuration:

1. **Runtime Detection**: Detect GPU at evaluation time
2. **Multi-GPU Support**: Better handling of multiple discrete GPUs
3. **Power Management**: Automatic GPU power management settings
4. **Performance Profiles**: Gaming vs. productivity configurations
5. **Display Configuration**: Integration with display management

## See Also

- [Virtualization Guide](../virtualization/readme.md) - GPU passthrough with VFIO
- [NixOS Hardware Configuration](https://nixos.org/manual/nixos/stable/index.html#sec-gpu)
- [Nvidia on NixOS](https://nixos.wiki/wiki/Nvidia)
- [AMD GPU on NixOS](https://nixos.wiki/wiki/AMD_GPU)
