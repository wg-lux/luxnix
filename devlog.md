# 2024-12-21
## traefik implementation
### Quick introduction
*Entrypoints*
- mostly :80 and :443 (http and https)

*Routers*

*Middlewares*

*Services*

# 2024-12-20
## Django Test App deployment
- add modules/home/luxnix/django-demo-app
  - home option: luxnix.django-demo-app
  - added to homes/x86_64-linux/admin@gc-06



# 2024-12-19
## setup gc-09
*Luxnix-Administration Repo*
```shell

cd ~/luxnix-administration

export SSH_IP="192.168.0.222"
export TARGET_HOSTNAME="gc-09"
export PUB_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M"

./deploy-authorized-key.sh nixos@$SSH_IP $PUB_KEY

## continue after installation

ssh $SSH_IP
sudo rm -rf /etc/user-passwords
sudo mkdir /etc/user-passwords  
sudo chown -R admin /etc/user-passwords
git clone https://github.com/wg-lux/luxnix
cd luxnix
direnv allow
exit

./deploy-user-folders-remote.sh "admin@$SSH_IP" "admin@$TARGET_HOSTNAME"

python luxnix_administration/utils/deploy_user_passwords_remote.py $TARGET_HOSTNAME $SSH_IP 

./deploy-openvpn-certificates-remote.sh admin@$SSH_IP $TARGET_HOSTNAME "client" nopass

ssh $SSH_IP
nh os switch
nh home switch
cd luxnix
sudo boot-decryption-stick-setup

```


```shell
cd ~/luxnix

export SSH_IP="192.168.0.222"
export TARGET_HOSTNAME="gc-09"

nixos-anywhere --flake '.#gc-09' nixos@$SSH_IP



```


## setup gc-07
*Luxnix-Administration Repo*
```shell

cd ~/luxnix-administration

export SSH_IP="192.168.0.221"
export TARGET_HOSTNAME="gc-07"
export PUB_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M"

./deploy-authorized-key.sh nixos@$SSH_IP $PUB_KEY

## continue after installation
./deploy-user-folders-remote.sh "admin@$SSH_IP" "admin@$TARGET_HOSTNAME"

python luxnix_administration/utils/deploy_user_passwords_remote.py $TARGET_HOSTNAME $SSH_IP 

./deploy-openvpn-certificates-remote.sh admin@$SSH_IP $TARGET_HOSTNAME "client" nopass

ssh $SSH_IP
nh os switch
nh home switch
cd luxnix
sudo boot-decryption-stick-setup

```


```shell
cd ~/luxnix

export SSH_IP="192.168.0.221"
export TARGET_HOSTNAME="gc-07"

nixos-anywhere --flake '.#gc-07' nixos@$SSH_IP


ssh $SSH_IP
sudo rm -rf /etc/user-passwords
sudo mkdir /etc/user-passwords  
sudo chown -R admin /etc/user-passwords
git clone https://github.com/wg-lux/luxnix
cd luxnix
direnv allow
exit
```

## setup gc-08
*Luxnix-Administration Repo*
```shell

cd ~/luxnix-administration

export SSH_IP="192.168.0.141"
export TARGET_HOSTNAME="gc-08"
export PUB_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M"

./deploy-authorized-key.sh nixos@$SSH_IP $PUB_KEY

# continue in luxnix shell and install os
# continue here after finished installation

ssh $SSH_IP
sudo rm -rf /etc/user-passwords
sudo mkdir /etc/user-passwords  
sudo chown -R admin /etc/user-passwords
git clone https://github.com/wg-lux/luxnix
cd luxnix
direnv allow
exit


./deploy-user-folders-remote.sh "admin@$SSH_IP" "admin@$TARGET_HOSTNAME"

python luxnix_administration/utils/deploy_user_passwords_remote.py $TARGET_HOSTNAME $SSH_IP 

./deploy-openvpn-certificates-remote.sh admin@$SSH_IP $TARGET_HOSTNAME "client" nopass

ssh $SSH_IP

nh os switch
nh home switch
cd luxnix
boot-decryption-stick-setup 

```


```shell
cd ~/luxnix

export SSH_IP="192.168.0.141"
export TARGET_HOSTNAME="gc-08"

nixos-anywhere --flake '.#gc-08' nixos@$SSH_IP


ssh $SSH_IP
sudo rm -rf /etc/user-passwords
sudo mkdir /etc/user-passwords  
sudo chown -R admin /etc/user-passwords
git clone https://github.com/wg-lux/luxnix
cd luxnix
direnv allow
exit
```

## gs-01 setup - new attempt
previously we failed due to inconsistent disk mounting (sda, sdb, ....)

*Luxnix-Administration Repo*
```shell

cd ~/luxnix-administration

export SSH_IP="192.168.0.230"
export TARGET_HOSTNAME="gs-01"
export PUB_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M"

./deploy-authorized-key.sh nixos@$SSH_IP $PUB_KEY


# continue in luxnix shell and install os
# continue here after finished installation

./deploy-user-folders-remote.sh "admin@$SSH_IP" "admin@$TARGET_HOSTNAME"

python luxnix_administration/utils/deploy_user_passwords_remote.py $TARGET_HOSTNAME $SSH_IP 

./deploy-openvpn-certificates-remote.sh admin@$SSH_IP $TARGET_HOSTNAME "client" nopass

ssh $SSH_IP

nh os switch
nh home switch
cd luxnix
sudo gs-01-bootstick


```

```shell
cd ~/luxnix
export SSH_IP="192.168.0.230"
export TARGET_HOSTNAME="gs-01"

nixos-anywhere --flake '.#gs-01' nixos@$SSH_IP


ssh $SSH_IP
sudo rm -rf /etc/user-passwords
sudo mkdir /etc/user-passwords  
sudo chown -R admin /etc/user-passwords
git clone https://github.com/wg-lux/luxnix
cd luxnix
direnv allow
exit
```

## s-04 setup
```shell

cd ~/luxnix-administration

export SSH_IP="192.168.1.48"
export TARGET_HOSTNAME="s-04"
export PUB_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M"

./deploy-authorized-key.sh nixos@$SSH_IP $PUB_KEY

cd ~/luxnix

export SSH_IP="192.168.1.48"
export TARGET_HOSTNAME="s-04"
export PUB_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M"

nixos-anywhere --flake '.#s-04' nixos@$SSH_IP
```

```shell

export SSH_IP="192.168.1.48"
export TARGET_HOSTNAME="s-04"

ssh $SSH_IP
sudo rm -rf /etc/user-passwords
sudo mkdir /etc/user-passwords  
sudo chown -R admin /etc/user-passwords
git clone https://github.com/wg-lux/luxnix
cd luxnix
direnv allow
exit

cd ~/luxnix-administration
export SSH_IP="192.168.1.48"
export TARGET_HOSTNAME="s-04"
./deploy-user-folders-remote.sh "admin@$SSH_IP" "admin@$TARGET_HOSTNAME"

python luxnix_administration/utils/deploy_user_passwords_remote.py $TARGET_HOSTNAME $SSH_IP 

./deploy-openvpn-certificates-remote.sh admin@$SSH_IP $TARGET_HOSTNAME "client" nopass

ssh $SSH_IP
nh os switch
nh home switch
cd luxnix
sudo boot-decryption-stick-setup

exit

# create systems/x86_64-linux/${TARGET_HOSTNAME}/boot-decryption-config.nix
# import created file in systems/x86_64-linux/${TARGET_HOSTNAME}/default.nix
git add .
git commit -m "add $TARGET_HOSTNAME decryption stick config"
git push

ssh $SSH_IP
cd luxnix
git add .
git stash
git pull
nho
sudo reboot

# cd ~/luxnix-administration/data/openvpn-ca/
# export SSH_IP="192.168.1.48"
# export TARGET_HOSTNAME="s-04"

# easyrsa build-client-full $TARGET_HOSTNAME



```

# 2024-12-18
## Deploy Boot Keyfiles on s-01, s-02, s-03
- add boot stick to base-server role

## setup gs-01
```shell

cd ~/luxnix-administration

export SSH_IP="192.168.0.228"
export TARGET_HOSTNAME="gs-01"
export PUB_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M"

./deploy-authorized-key.sh nixos@$SSH_IP $PUB_KEY

cd ~/luxnix

export SSH_IP="192.168.0.228"
export TARGET_HOSTNAME="gs-01"
export PUB_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M"

nixos-anywhere --flake '.#gs-01' nixos@$SSH_IP

```

```shell

export SSH_IP="192.168.0.228"
export TARGET_HOSTNAME="gs-01"

./deploy-user-folders-remote.sh "admin@$SSH_IP" "admin@$TARGET_HOSTNAME"

python luxnix_administration/utils/deploy_user_passwords_remote.py $TARGET_HOSTNAME $SSH_IP 

sudo boot-decryption-stick-setup

cd ~/luxnix-administration/data/openvpn-ca/
export SSH_IP="192.168.0.228"
export TARGET_HOSTNAME="gs-01"

easyrsa build-client-full $TARGET_HOSTNAME

./deploy-openvpn-certificates-remote.sh admin@$SSH_IP $TARGET_HOSTNAME "client" nopass

```


## Setup s-04
```shell

export SSH_IP="192.168.1.48"
export TARGET_HOSTNAME="s-04"
export PUB_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M"

cd ~/luxnix-administration
./deploy-authorized-key.sh nixos@$SSH_IP $PUB_KEY

# create admin@s-04
# create system folder s04
# modify disk (sda) and hardware config (kernel modules, intel cpu)

cd ~/luxnix
git add .
git commit -m "add $TARGET_HOSTNAME"
git push

nixos-anywhere --flake '.#s-04' nixos@$SSH_IP

```

### setup gs-02

```shell
export SSH_IP="172.16.255.22"
export TARGET_HOSTNAME="gs-02"

ssh $SSH_IP

sudo rm -rf /etc/user-passwords
sudo mkdir /etc/user-passwords  
sudo chown -R admin /etc/user-passwords

cd luxnix
git pull 
nho
```

```shell
cd ~/luxnix-administration
export SSH_IP="172.16.255.22"
export TARGET_HOSTNAME="gs-02"

./deploy-user-folders-remote.sh "admin@$SSH_IP" "admin@$TARGET_HOSTNAME"

python luxnix_administration/utils/deploy_user_passwords_remote.py $TARGET_HOSTNAME $SSH_IP 

sudo boot-decryption-stick-setup

```

### s-03
```shell
export SSH_IP="192.168.1.24"
export TARGET_HOSTNAME="s-03"

ssh $SSH_IP
git pull 
nho

sudo boot-decryption-stick-setup


```

*Detour: Deploy User-folders and passwords*
Target
```shell
sudo rm -rf /etc/user-passwords
sudo mkdir /etc/user-passwords  
sudo chown -R admin /etc/user-passwords 
```

Source
```shell
cd ~/luxnix-administration
export SSH_IP="192.168.1.24"
export TARGET_HOSTNAME="s-03"

./deploy-user-folders-remote.sh "admin@$SSH_IP" "admin@$TARGET_HOSTNAME"

python luxnix_administration/utils/deploy_user_passwords_remote.py $TARGET_HOSTNAME $SSH_IP 


./deploy-openvpn-certificates-remote.sh "admin@$SSH_IP" "$TARGET_HOSTNAME" "client"

```

### s-02
export SSH_IP="192.168.179.2"
export TARGET_HOSTNAME="s-02"

ssh $SSH_IP

cd luxnix
git pull 
nho

sudo boot-decryption-stick-setup
git add .
git stash

--- 
on source machine

- nano systems/x86_64-linux/$TARGET_HOSTNAME/boot-decryption-config.nix 
- nano systems/x86_64-linux/$TARGET_HOSTNAME/default.nix
    - add ./boot-decryption-config.nix to extraImports

- git add .
- git commit -m "added $TARGET decryption stick config"

---
on target machine

- git pull
- nho


### s-01
ssh 192.168.179.1
cd luxnix
git pull
nho

```shell
❯ sudo boot-decryption-stick-setup
Available USB devices:
sda             7,5G disk  
nvme0n1       476,9G disk  
Please enter the device path (e.g., /dev/sdb) of the USB drive: /dev/sda 
```

- create `boot-decryption-config.nix` file in target systems folder in nix config:
    - `nano systems/x86_64-linux/s-01/boot-decryption-config.nix`
- add to extra imports in `nano systems/x86_64-linux/s-01/default.nix`

- git add .
- pull and rebuild on target system


- [x] add echo cat generated-nix-config-file to script

# 2024-12-17
## setup gs-02

```shell
export TARGET_IP="192.168.0.219"

ssh nixos@$TARGET_IP

sudo nixos-generate-config 

cat /etc/nixos/hardware-configuration
```

```nix
# Do not modify this file!  It was generated by ‘nixos-generate-config’
# and may be overwritten by future invocations.  Please make changes
# to /etc/nixos/configuration.nix instead.
{ config, lib, pkgs, modulesPath, ... }:

{
  imports =
    [ (modulesPath + "/installer/scan/not-detected.nix")
    ];

  boot.initrd.availableKernelModules = [ "nvme" "xhci_pci" "ahci" "thunderbolt" "usb_storage" "usbhid" "sd_mod" ];
  boot.initrd.kernelModules = [ ];
  boot.kernelModules = [ "kvm-amd" ];
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
  # networking.interfaces.enp19s0u2u3.useDHCP = lib.mkDefault true;

  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
  hardware.cpu.amd.updateMicrocode = lib.mkDefault config.hardware.enableRedistributableFirmware;
}

```
-> created `systems/x86_64-linux/gs-02/hardware-configuration.nix`

create disk configuration
```shell
[nixos@nixos:~]$ lsblk
NAME        MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
loop0         7:0    0  2.3G  0 loop /nix/.ro-store
sda           8:0    1 14.6G  0 disk 
└─sda1        8:1    1 14.6G  0 part /iso
nvme2n1     259:0    0  3.6T  0 disk 
nvme3n1     259:1    0  3.6T  0 disk 
nvme1n1     259:2    0  3.6T  0 disk 
nvme0n1     259:3    0  3.6T  0 disk 
├─nvme0n1p1 259:4    0    1G  0 part 
└─nvme0n1p2 259:5    0  3.6T  0 part 
```
-> -> created `systems/x86_64-linux/gs-02/disks.nix`

```shell
# deploy authorized_key
nano .ssh/authorized_keys

ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M

exit

nixos-anywhere --flake '.#gs-02' $IP


```

### Deploy Secrets
- switch to luxnix administration
```shell
# (on target machine)
sudo rm /etc/user-passwords/admin_hashed
sudo rm /etc/user-passwords/dev-01_hashed
sudo rm /etc/user-passwords/user_hashed

##################

# On source machine
python ./luxnix_administration/utils/deploy_user_passwords_remote.py "gs-02" "192.168.0.219"


cd ~/luxnix-administration/data/openvpn-ca/

easyrsa build-client-full gs-02

./deploy-openvpn-certificates-remote.sh admin@192.168.0.219 "gs-02" "client" nopass

# Generate new certificates
python
from luxnix_administration.utils import generate_client_certificate_folder

# host
generate_client_certificate_folder(
    cert_type = "client",
    hostname = "gs-02"
)

exit() #exit python

./deploy-openvpn-certificates-remote.sh admin@192.168.0.219 gs-02 client

reboot

```

## Migrate S01 User Passwords
- luxnix-administration
    - update user passwords on

```shell
cd ~/luxnix-administration
# set hostname and ip as environment variables
export HOSTNAME="s-01"
export IP="192.168.179.1"
export SCRIPTPATH="./luxnix_administration/utils/deploy_user_passwords_remote.py"

python $SCRIPTPATH $HOSTNAME $IP

ssh admin@$IP
nho



```



# Before 2024-12-17
To-Do

    Migrate Tempfile Rules
    Migrate user passwords
    Create coloreg-client role
        two bootmodes, one with (maintenance), one w/o (production) ssh access
        implement impermanence setup to make sure no temporary files remain between boots
    deploy usb-encrypter
        create test using virtual usb stick
    deploy create-boot-usb script

Traefik as Reverse Proxy

VPN Configuration

    defined in modules/nixos/vpn

Identities
Computer (auto generated on machine creation)

    /etc/machine-id
    /etc/ssh/ssh_host_ed25519_key
    /etc/ssh/ssh_host_rsa_key

--> collect and store in luxnix-administration/data/computer-identities/{host}
User

-> See: deployment-guid.md

For standalone setup manually deploy your personal ed_25519 key to

    ~/.ssh/id_ed25519
        if you want, you can also generate a new one: ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
    You can add the key to yout git account git!

OpenVPN

-> See: deployment-guid.md

Clients require (/etc/identity/openvpn/):

    private key (gc-01.key -> cert.key)
    certificate (gc-01.crt -> cert.crt)
    server certificate: ca.cert
    pre-shared key: ta.key

Acknowledgements

    https://github.com/hmajid2301/nixicle
    https://haseebmajid.dev/posts/2024-05-02-part-5b-installing-our-nix-configuration-as-part-of-your-workflow/

Scratchpad / Prototyping

nixos-anywhere --flake '.#server-03' nixos@192.168.179.3

identities = { ed25519 = { # ed25519 keys backup = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC/gVfFAeG/9CwqiPOxu5JoY/vx705a77wvGgh687a5d"; gpu-client-dev = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHwYnbv/tPCcTIPgFbOISXDOiGZGpyUtu6NmtJ+Pg9Dh agl-gpu-client-dev"; gpu-client-06 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMenwtVZxjgAWj6xKZqB40QTl9smUcaoDnTRmJ/icp29 lux@gc06"; }; };
Certificate Authority
GC 07
nixos-anywhere --flake '.#gc-03' nixos@192.168.0.48