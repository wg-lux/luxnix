# Luxnix Generic Settings Module

The generic-settings module provides core system configuration options that are shared across all Luxnix systems. This includes system metadata, network settings, database configuration, and automatic hardware configuration.

## Overview

This module handles:

1. **System Configuration** - State version, platform, language settings
2. **Network Settings** - VPN, Traefik, SSL certificates
3. **Database Configuration** - PostgreSQL settings and authentication
4. **Security Settings** - Sensitive service groups, secret management
5. **Hardware Configuration** - Automatic CPU and GPU detection/configuration
6. **User Management** - Admin users and group memberships

## Quick Start

Basic configuration:

```nix
{
  luxnix.generic-settings = {
    enable = true;
    systemStateVersion = "23.11";
    hostPlatform = "x86_64-linux";
    
    # Optional: Automatic GPU configuration
    gpu = {
      autoDetect = true;
      type = "auto";
    };
  };
}
```

## Core Settings

### System Information

```nix
luxnix.generic-settings = {
  systemStateVersion = "23.11";         # NixOS state version
  hostPlatform = "x86_64-linux";        # Target platform
  language = "german";                  # "english" | "german"
  mutableUsers = false;                 # Allow user mutations
  useDHCP = true;                       # Use DHCP networking
};
```

### Network Configuration

```nix
luxnix.generic-settings = {
  vpnIp = "172.16.255.106";                    # This host's VPN IP
  vpnSubnet = "172.16.255.0/24";               # VPN network subnet
  adminVpnIp = "172.16.255.106";               # Admin host VPN IP
  
  traefikHostDomain = "traefik.endoreg.local"; # Traefik dashboard domain
  traefikHostIp = "172.16.255.106";            # Traefik host IP
  
  # SSL Certificate paths
  sslCertificateKeyPath = "/home/admin/.ssl/endo-reg-net.key";
  sslCertificatePath = "/home/admin/.ssl/__endo-reg_net.pem";
};
```

### Security Settings

```nix
luxnix.generic-settings = {
  secretDir = "/etc/secrets";                  # Secret storage directory
  sensitiveServiceGroupName = "sensitiveServices";  # Group for sensitive services
  sensitiveServiceGID = 901;                   # GID for sensitive group
  
  # SMTP configuration paths
  smtpUserFilePath = "/etc/secrets/vault/smtp_user";
  smtpPwdFilePath = "/etc/secrets/vault/smtp_pwd";
};
```

### System Paths

```nix
luxnix.generic-settings = {
  configurationPath = "/home/admin/lx-production/"; # Full config path
  systemConfigurationPath = "/home/admin/lx-production/systems/x86_64-linux/hostname";
  
  rootIdED25519 = "ssh-ed25519 AAAA...";          # Root SSH key
};
```

## Hardware Configuration

### Automatic GPU Configuration

The module includes automatic GPU detection and configuration:

```nix
luxnix.generic-settings.gpu = {
  autoDetect = true;              # Enable auto-detection
  type = "auto";                  # "nvidia" | "amd" | "intel" | "auto"
  
  nvidia = {
    enable = true;                # Enable Nvidia support
    driver = "beta";              # "stable" | "beta" | "production"
    
    prime = {
      enable = false;             # Enable for hybrid graphics
      nvidiaBusId = "PCI:01:00:0";
      onboardBusId = "PCI:00:02:0";
      onboardType = "intel";
    };
  };
  
  amd = {
    enable = false;
    openSource = true;            # Use open-source drivers
  };
  
  intel = {
    enable = false;
    vaapi = true;                 # Enable hardware acceleration
  };
};
```

For detailed GPU configuration, see [GPU Configuration Guide](gpu-readme.md).

## Database Configuration

### PostgreSQL Settings

```nix
luxnix.generic-settings.postgres = {
  enable = true;
  
  remote = {
    admin = {
      enable = true;
      vpnIp = "172.16.255.106";        # Admin connection IP
    };
  };
  
  extraAuthentication = '''
    # Custom authentication rules
    host all admin 172.16.255.106/32 md5
  ''';
  
  extraIdentMap = '''
    # Custom identity mapping
  ''';
};
```

## Integration Features

### Sensitive Service Groups

The module automatically creates and manages sensitive service groups:

```nix
# Automatically created group
users.groups.sensitiveServices = {
  gid = 901;
  members = [ 
    "admin"                    # Always includes admin user
    "keycloak"                 # Added if Keycloak role is enabled
  ];
};
```

### User Management

Admin users are automatically configured with appropriate group memberships for:

- Sensitive services management
- PostgreSQL administration (if enabled)
- Keycloak management (if enabled)

### Validation and Warnings

The module provides built-in validation:

```nix
# Example warnings
warnings = [
  "GPU auto-detection is enabled but type is manually set"
  "Nvidia PRIME is enabled but Nvidia GPU support is disabled"
];
```

## Example Configurations

### Basic Server

```nix
{
  luxnix.generic-settings = {
    enable = true;
    systemStateVersion = "23.11";
    hostPlatform = "x86_64-linux";
    
    vpnIp = "172.16.255.10";
    postgres.enable = true;
  };
}
```

### Gaming Workstation

```nix
{
  luxnix.generic-settings = {
    enable = true;
    systemStateVersion = "23.11";
    language = "english";
    
    gpu = {
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
  };
}
```

### Development Server

```nix
{
  luxnix.generic-settings = {
    enable = true;
    systemStateVersion = "23.11";
    
    postgres = {
      enable = true;
      remote.admin.enable = true;
    };
    
  };
}
```

## Module Integration

This module integrates with other Luxnix modules:

- **postgres role**: Automatic enable based on postgres.enable
- **keycloak role**: Automatic group membership management
- **nvidia-prime/nvidia-default**: GPU configuration delegation
- **virtualization**: Shared sensitive service groups

## Migration Guide

### From Manual GPU Configuration

Replace manual GPU module configuration:

```nix
# Old
luxnix.nvidia-prime = {
  enable = true;
  nvidiaBusId = "PCI:01:00:0";
  onboardBusId = "PCI:00:02:0";
  onboardGpuType = "intel";
  nvidiaDriver = "beta";
};

# New  
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

### From Manual Group Management

The module now handles sensitive service groups automatically:

```nix
# Old - manual group management
users.groups.sensitive-service-group = {
  gid = 901;
  members = ["admin"];
};

# New - automatic management
luxnix.generic-settings = {
  sensitiveServiceGroupName = "sensitiveServices";
  sensitiveServiceGID = 901;
};
```

## See Also

- [GPU Configuration Guide](gpu-readme.md) - Detailed GPU setup
- [Virtualization Guide](../../../../docs/virtualization-guide.md) - VFIO and GPU passthrough
- [Vault Setup](../../../../docs/vault-setup.md) - Secret bootstrap and lifecycle
- [SSH Host Identity](../../../../docs/ssh-host-identity.md) - Host-key verification and rotation
- [Network Architecture](../../../../docs/network-architecture.md) - Network setup
