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
    };

  services = {
    };

  luxnix = {
    boot-decryption-stick.enable = true;

generic-settings.enable = true;

generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;

maintenance.autoUpdates.dates = "04:00";

maintenance.autoUpdates.enable = true;

maintenance.autoUpdates.flake = "github:wg-lux/luxnix";

nvidia-prime.enable = false;

vault.dir = "/etc/secrets/vault";

vault.enable = true;

vault.key = "/etc/secrets/.key";

vault.psk = "/etc/secrets/.psk";

postgres.main.authentication = ''
#type database DBuser address auth-method optional_ident_map
local sameuser all peer map=superuser_map
host  all all 172.16.255.106/32 scram-sha-256 map=superuser_map
host  replication ${config.roles.postgres.main.replUser} 172.16.255.106/32 scram-sha-256
host  ${config.roles.postgres.main.devUser} ${config.roles.postgres.main.devUser} 172.16.255.106/32 scram-sha-256
''; 
  postgres.main.enable = true;

postgres.main.identMap = ''
# ArbitraryMapName systemUser DBUser
superuser_map      root      postgres
superuser_map      root      ${config.roles.postgres.main.replUser}
superuser_map      ${config.user.admin.name}     ${config.user.admin.name}
superuser_map      ${config.user.admin.name}     endoregClient
superuser_map      postgres  postgres

# Let other names login as themselves
superuser_map      /^(.*)$   \1
''; 
  generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "intel";

generic-settings.linux.initrd.availableKernelModules = ["xhci_pci" "ahci" "usbhid" "nvme" "usb_storage" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["nfs" "btrfs"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.linux.kernelModules = ["kvm-intel"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.systemStateVersion = "23.11";

};
}