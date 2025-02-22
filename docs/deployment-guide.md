# Deployment

This example will deploy server 2 (s-02)

Establishing luxnix on your machine requires using the official nix installer first.

For this step, follow the guide at https://nixos.wiki/wiki/NixOS_Installation_Guide.

Once Luxnix is established on the central study laptop, it can be deployed to other machines. These should be accessible during setup, later connections via a secure ssh connection will be available.

For this, the user roles are defined in the homes directory.

## Pre-Requisites
- NixOS Boot Stick
- Source Machine running Nix with repos: `luxnix`and `luxnix-administration`
- Target machine which will be assigned the same local ip address

## Luxnix installation
- Boot to NixOS Installer. Deactivate secure boot if required.
- set user password in terminal: `passwd`
- get ip address: `ifconfig`
- ssh connect using password authentication (nixos@ip)
- deploy your ed25519 public key: `nano ~/.ssh/authorized_keys`
    - To view your key: `cat ~/.ssh/id_ed25519.pub

```shell
ssh nixos@192.168.179.142

nano ~/.ssh/authorized_keys

ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M
```

or 
```shell
./deploy-authorized-key.sh nixos@192.168.179.2 "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M"
```

- verify ssh connection: `ssh nixos@192.168.179.142`
- generate hardware config `sudo nixos-generate-config`
- view. `cat /etc/nixos/hardware-configuration.nix `

*Example*
```nix
# Do not modify this file!  It was generated by ‘nixos-generate-config’
# and may be overwritten by future invocations.  Please make changes
# to /etc/nixos/configuration.nix instead.
{ config, lib, pkgs, modulesPath, ... }:

{
  imports =
    [ (modulesPath + "/installer/scan/not-detected.nix")
    ];

  boot.initrd.availableKernelModules = [ "xhci_pci" "ahci" "nvme" "usb_storage" "sd_mod" ];
  boot.initrd.kernelModules = [ ];
  boot.kernelModules = [ "kvm-intel" ];
  boot.extraModulePackages = [ ];

  fileSystems."/" =
    { device = "tmpfs";
      fsType = "tmpfs";
    };

  fileSystems."/iso" =
    { device = "/dev/disk/by-uuid/2EFC-066E";
      fsType = "vfat";
      options = [ "fmask=0022" "dmask=0022" ];
    };

  fileSystems."/nix/.ro-store" =
    { device = "/iso/nix-store.squashfs";
      fsType = "squashfs";
      options = [ "loop" ];
    };

  fileSystems."/nix/.rw-store" =
    { device = "tmpfs";
      fsType = "tmpfs";
    };

  fileSystems."/nix/store" =
    { device = "overlay";
      fsType = "overlay";
    };

  swapDevices = [ ];

  # Enables DHCP on each ethernet and wireless interface. In case of scripted networking
  # (the default) this is the recommended approach. When using systemd-networkd it's
  # still possible to use this option, but it's recommended to use it in conjunction
  # with explicit per-interface declarations with `networking.interfaces.<interface>.useDHCP`.
  networking.useDHCP = lib.mkDefault true;
  # networking.interfaces.enp4s0.useDHCP = lib.mkDefault true;
  # networking.interfaces.wlo1.useDHCP = lib.mkDefault true;

  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
  hardware.cpu.intel.updateMicrocode = lib.mkDefault config.hardware.enableRedistributableFirmware;
}
```

*Extract relevant info and store to `systems/x86_64-linux/{hostname}/hardware-configuration.nix`, Example:*

```nix
# Do not modify this file!  It was generated by ‘nixos-generate-config’
# and may be overwritten by future invocations.  Please make changes
# to /etc/nixos/configuration.nix instead.
{
  config,
  lib,
  modulesPath,
  ...
}: {
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
  ];

  boot.initrd.availableKernelModules = [ "xhci_pci" "ahci" "nvme" "usb_storage" "sd_mod" ];
  boot.initrd.kernelModules = [ ];
  boot.kernelModules = [ "kvm-intel" ];
  boot.extraModulePackages = [ ];

  networking.useDHCP = lib.mkDefault true;

  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
  hardware.cpu.intel.updateMicrocode = lib.mkDefault config.hardware.enableRedistributableFirmware;

}
```
*Verify disk setup:*
- Run `lsblk`

```shell
[nixos@nixos:~]$ lsblk
NAME        MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
loop0         7:0    0   2.3G  0 loop /nix/.ro-store
sda           8:0    1  14.6G  0 disk 
└─sda1        8:1    1  14.6G  0 part /iso
nvme0n1     259:0    0 476.9G  0 disk 
├─nvme0n1p1 259:1    0   512M  0 part 
├─nvme0n1p2 259:2    0 459.6G  0 part 
└─nvme0n1p3 259:3    0  16.9G  0 part 

```

- Verify / Adapt disk setup (`systems/x86_64-linux/{hostname}/disks.nix`)

>[!Warning]
>in case of a pre-existing encrypted file system do the following
>- create empty partition table
>- create new ext4 filesystem

*Verify NVIDIA Setup in `systems/x86_64-linux/{hostname}/default.nix` using `lspci`*
```nix
  {
        luxnix.nvidia-prime = {
        enable = true; # enables common and desktop (with addon plasma) roles
        nvidiaBusId = "PCI:1:0:0";
        onboardBusId = "PCI:0:2:0";
        onboardGpuType = "intel";
        nvidiaDriver = "beta";
    };
  }
```

*Generate User Home Configuration*
Create home configuration for your user, e.g.: `homes/x86_64-linux/admin@gc-02/default.nix

*Run installer*
- Make sure all newly created files are committed!
- Run: `nixos-anywhere --flake '.#gc-02' nixos@192.168.1.47`
- Enter & Verify Harddisk encryption key


## Initial System Configuration

- Log in as admin user
- git clone https://github.com/wg-lux/luxnix
- rm ~/.zshrc
- cd luxnix
- nh os switch
- nh home switch
- sudo chown -R admin:root "/etc/user-passwords" (necessary for remote deploy w/o sudo priv.)
- reboot


## Prepare OpenVPN ID Files
```python
from luxnix_administration.utils import generate_client_certificate_folder

# host
generate_client_certificate_folder(cert_type= $CERT_TYPE, hostname= $HOSTNAME)

# client
generate_client_certificate_folder(cert_type= "client", hostname= "s-02")

```

## Deploy Secrets / IDs using luxnix administration

For "admin" on "gc-02":
- `./deploy-user-folders-remote.sh "admin@192.168.179.2" "admin@s-02"`

- Deploy password for user:
a. locally: 
`python ./luxnix_administration/utils/deploy_user_passwords_local.py "gc-02"`

b. remotely:
`python ./luxnix_administration/utils/deploy_user_passwords_remote.py "s-02" "192.168.179.2" "dev-01"`

- Deploy OpenVPN Config / Certs
- run: `./deploy-openvpn-certificates.sh NAME TYPE` for local deployment
(e.g., `./deploy-openvpn-certificates.sh gc-02 client`)
- remote: `./deploy-openvpn-certificates-remote.sh <user@ip> <hostname> <cert_type>`
(e.g.`./deploy-openvpn-certificates-remote.sh admin@192.168.179.2 s-02 client`) 

# Setup Boot USB Stick
- set `options.luxnix.boot-decryption-stick` true
  - enabled by roles `base-server`, `endoreg-client`

# EndoReg Client: Sensitive Data Hdd
- git clone https://github.com/wg-lux/endoreg-usb-encrypter
- insert empty USB Stick (Stick will be formatted / erased)
- make sure the option "endoreg.sensitive-storage.enabled" is true 

- run `sudo python runner.py`
- backup keyfiles if required
- make sure you copy sensitive-storage.nix (was sensitive-hdd.nix) to your system folder
- deploy generated keyfiles (1 -> dropoff, 2 -> processing, 3 -> processed) to ~/admin/.config/endoreg-sensitive-storage

*Verify Functionality*

```shell
sudo mount-dropoff
sudo umount-dropoff
sudo log-dropoff

sudo mount-processing
sudo umount-processing
sudo log-processing

sudo mount-processed
sudo umount-processed
sudo log-processed
```