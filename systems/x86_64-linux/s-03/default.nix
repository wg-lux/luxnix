# /default.nix

{ config, pkgs, lib, modulesPath, ... }:

{
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
    ./boot-decryption-config.nix
    ./disks.nix
  ];

  user = {
    admin = {
      name = "admin";
    };
    ansible.enable = true;
    settings.mutable = false;
  };

  roles = { 
    aglnet.client.enable = true;
    base-server.enable = true;
    endoreg-client.enable = false;
    ssh-access.dev-03.enable = true;
    ssh-access.dev-03.idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDBJcYjGNIwOUs+KG8TbBxPWtJFEqni0p+1J5Yz++Aos";
    postgres.main.enable = true;
    };

  services = {
    };

  luxnix = {
    boot-decryption-stick.enable = true;

dns.enable = true;

generic-settings.adminVpnIp = "172.16.255.106";

generic-settings.enable = true;

generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;

generic-settings.traefikHostDomain = "traefik.endoreg.local";

generic-settings.traefikHostIp = "172.16.255.12";

maintenance.autoUpdates.dates = "04:00";

maintenance.autoUpdates.enable = true;

maintenance.autoUpdates.flake = "github:wg-lux/luxnix";

nvidia-prime.enable = false;

vault.dir = "/etc/secrets/vault";

vault.enable = true;

vault.key = "/etc/secrets/.key";

vault.psk = "/etc/secrets/.psk";

generic-settings.postgres.activeAuthentication = ''
#type database DBuser address auth-method optional_ident_map
local sameuser all peer map=superuser_map
host  all all ${config.luxnix.generic-settings.adminVpnIp}/32 scram-sha-256
host  replication ${config.roles.postgres.main.replUser} ${config.luxnix.generic-settings.adminVpnIp}/32 scram-sha-256
host  ${config.roles.postgres.main.devUser} ${config.roles.postgres.main.devUser} ${config.luxnix.generic-settings.adminVpnIp}/32 scram-sha-256
host  all postgres ${config.luxnix.generic-settings.adminVpnIp}/32 scram-sha-256
# dev-01
host  all all 172.16.255.102/32 scram-sha-256
host  all postgres 172.16.255.102/32 scram-sha-256
# dev-02
host  all all 172.16.255.108/32 scram-sha-256
host  all postgres 172.16.255.108/32 scram-sha-256
''; 
  generic-settings.postgres.activeIdentMap = ''
# ArbitraryMapName systemUser DBUser
superuser_map      root      postgres
superuser_map      root      ${config.roles.postgres.main.replUser}
superuser_map      ${config.user.admin.name}     ${config.user.admin.name}
superuser_map      ${config.user.admin.name}     postgres
superuser_map      ${config.user.admin.name}     endoregClient
superuser_map      postgres  postgres

# Let other names login as themselves
superuser_map      /^(.*)$   \1
''; 
  generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "amd";

generic-settings.linux.initrd.availableKernelModules = ["xhci_pci" "ahci" "usbhid" "nvme" "usb_storage" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["nfs" "btrfs"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.linux.kernelModules = ["kvm-amd"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.systemStateVersion = "23.11";

generic-settings.vpnIp = "172.16.255.13";

};
}