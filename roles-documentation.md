# Roles

## monitoring

### center-client

## aglnet

### client

#### Options

- `enable`: Enable aglnet-host OpenVPN configuration.
- `networkName`: The network name for the VPN.
- `mainDomain`: The main domain for the VPN.
- `port`: Port for the VPN.
- `protocol`: Protocol for the VPN.
- `protocolLc`: Lowercase protocol for the VPN.
- `noBind`: Whether to add 'nobind' to config.
- `restartAfterSleep`: Restart VPN after sleep.
- `autoStart`: Autostart VPN on boot.
- `updateResolvConf`: Update resolv.conf with VPN nameservers.
- `resolvRetry`: Resolv retry for the VPN.
- `dev`: Device for the VPN.
- `subnet`: Subnet for the VPN.
- `subnetIntern`: Subnet intern for the VPN.
- `keepalive`: Keepalive for the VPN.
- `cipher`: Cipher for the VPN.
- `verbosity`: Verbosity for the VPN.
- `caPath`: Path to CA certificate.
- `tlsAuthPath`: Path to TLS auth key.
- `serverCertPath`: Path to server certificate.
- `serverKeyPath`: Path to server key.
- `persistKey`: Persist key for the VPN.
- `persistTun`: Persist tun for the VPN.

#### Resulting Config Changes

- Installs `openvpn` package.
- Creates `/etc/openvpn` directory with appropriate permissions.
- Configures OpenVPN client with the specified options.
- Adds systemd service for OpenVPN with the specified options.

### host

#### Options

- `enable`: Enable aglnet-host OpenVPN configuration.
- `networkName`: The network name for the VPN.
- `mainDomain`: The main domain for the VPN.
- `backupNameservers`: Backup nameservers for the VPN.
- `port`: Port for the VPN. _(default: 1194)_
- `protocol`: Protocol for the VPN. _(default: "TCP")_
- `protocolLc`: Lowercase protocol for the VPN. _(default: "tcp")_
- `restartAfterSleep`: Restart VPN after sleep. _(default: true)_
- `autoStart`: Autostart VPN on boot. _(default: true)_
- `updateResolvConf`: Update resolv.conf with VPN nameservers. _(default: false)_
- `resolvRetry`: Resolv retry for the VPN. _(default: "infinite")_
- `dev`: Device for the VPN. _(default: "tun")_
- `subnet`: Subnet for the VPN. _(default: "172.16.255.0")_
- `subnetIntern`: Subnet intern for the VPN. _(default: "255.255.255.0")_
- `subnetSuffix`: Subnet suffix for the VPN. _(default: "32")_
- `keepalive`: Keepalive for the VPN. _(default: "10 1200")_
- `cipher`: Cipher for the VPN. _(default: "AES-256-GCM")_
- `verbosity`: Verbosity for the VPN. _(default: "3")_
- `caPath`: Path to CA certificate. _(default: "/etc/openvpn/ca.pem")_
- `tlsAuthPath`: Path to TLS auth key. _(default: "/etc/openvpn/tls.pem")_
- `serverCertPath`: Path to server certificate. _(default: "/etc/openvpn/crt.crt")_
- `serverKeyPath`: Path to server key. _(default: "/etc/openvpn/key.key")_
- `dhPath`: Path to DH parameters. _(default: "/etc/openvpn/dh.pem")_
- `clientConfigDir`: Path to client configuration directory. _(default: "/etc/openvpn/ccd")_
- `topology`: Topology for the VPN. _(default: "subnet")_
- `persistKey`: Persist key for the VPN. _(default: true)_
- `persistTun`: Persist tun for the VPN. _(default: true)_
- `client-to-client`: Enable client-to-client communication for the VPN. _(default: true)_

#### Resulting Config Changes

- Installs `openvpn` package.
- Creates `/etc/openvpn` directory with appropriate permissions.
- Configures OpenVPN host with the specified options.
- Adds systemd service for OpenVPN with the specified options.
- Configures firewall to allow VPN traffic.
- Sets backup nameservers for the VPN.

# base-server

## base-server

### Options

- `enable`: Enable base desktop server configuration.

### Resulting Config Changes

- Enables SSH service and sets authorized keys.
- Enables `nix-ld` with specified libraries.
- Configures boot binfmt for emulated systems.
- Enables desktop role.
- Disables `luxnix.avahi` and `virtualisation.podman` services.
- Installs `vscode` as a system package.

# Common

- **Enable Common Configuration**: Option to enable or disable the common configuration role.
- **Additional Packages**: Installs a default set of packages including development tools, disk utilities, and security tools.
- **System Packages**: Adds specified packages to the system environment.
- **Systemd Services**: Disables `NetworkManager-wait-online` and `systemd-networkd-wait-online` services to improve boot times.
- **Security Settings**: Enables `rtkit` for real-time scheduling and `sops` for secret management.
- **Programs**: Enables `coolercontrol` for hardware management, and CLI programs `nh` and `nix-ld`.
- **Temporary Files**: Configures systemd to create a secure directory for user passwords.
- **Roles**: Enables the default PostgreSQL role.
- **Hardware Configuration**: Ensures networking and graphics hardware support is enabled.
- **Nixpkgs Configuration**: Sets the host platform according to generic settings.

# Desktop

# Desktop Role Documentation

## Overview

- **Enable Desktop Configuration**: Option to enable or disable the desktop configuration role.
- **Boot Configuration**: Configures binfmt for emulated systems (e.g., aarch64-linux).
- **Roles**:
  - **Common Role**: Ensures the common role is enabled.
  - **Desktop Addons**: Enables Plasma desktop environment.
  - **Custom Packages**: Includes base development packages.
- **Hardware Configuration**:
  - **Audio**: Enables audio support.
  - **Bluetooth**: Enables Bluetooth support.

## Desktop Addon - Plasma

- **Enable Plasma Desktop Environment**: Option to enable or disable the Plasma DE.
- **Custom Packages**: Includes KDE Plasma packages.
- **Desktop Manager**:
  - Enables Plasma 6 desktop manager.
  - Sets the default session to `plasmax11`.
  - Enables SDDM as the display manager.
- **X Server Configuration**:
  - Enables the X server.
  - Sets the keyboard layout to German (`de`).
  - Configures the display manager settings, ensuring GDM is disabled and auto-suspend is turned off.

# Endoreg-client

# Endoreg Client Role Documentation

## Overview

The endoreg client role configuration in NixOS provides settings and packages specifically for configuring an Endoreg client environment.

## Configuration Summary

- **Enable Endoreg Client Configuration**: Option to enable or disable the Endoreg client configuration role.
- **User Configuration**: Enables the `endoreg-service-user`.
- **SSH Service**:
  - Enables the SSH service.
  - Adds authorized keys for the admin user (does not enable SSH by itself).
- **Systemd Temporary Files**:
  - Configures a secure directory for USB encrypter data at endoreg-sensitive-data with appropriate permissions. #TODO Migrate to own role
