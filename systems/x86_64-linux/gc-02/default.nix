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
    endoreg-client.enable = true;
    postgres.default.enable = true;
    custom-packages.baseDevelopment = true;
    };

  services = {
    };

  luxnix = {
    boot-decryption-stick.enable = true;

generic-settings.postgres.activeAuthentication = ''
#type database DBuser address auth-method optional_ident_map
local sameuser all peer map=superuser_map
host postgres postgres 127.0.0.1/32 scram-sha-256
host ${config.roles.postgres.default.defaultDbName} ${config.roles.postgres.default.defaultDbName} 127.0.0.1/32 scram-sha-256
''; 
  generic-settings.postgres.activeIdentMap = ''
# ArbitraryMapName systemUser DBUser
superuser_map      root      postgres
superuser_map      root      ${config.roles.postgres.main.replUser}
superuser_map      ${config.user.admin.name}     ${config.user.admin.name}
superuser_map      ${config.user.admin.name}     postgres
superuser_map      ${config.user.admin.name}     endoregClient
superuser_map      ${config.user.admin.name} ${config.roles.postgres.default.defaultDbName}
superuser_map      postgres  postgres

# Let other names login as themselves
superuser_map      /^(.*)$   \1
''; 
  generic-settings.adminVpnIp = "172.16.255.106";

generic-settings.configurationPathRelative = "luxnix";

generic-settings.enable = true;

generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;

gpu-eval.enable = true;

maintenance.autoUpdates.dates = "09:00";

maintenance.autoUpdates.enable = true;

maintenance.autoUpdates.flake = "github:wg-lux/luxnix";

maintenance.autoUpdates.operation = "switch";

nvidia-prime.enable = true;

nvidia-prime.nvidiaDriver = "beta";

vault.dir = "/etc/secrets/vault";

vault.enable = true;

vault.key = "/etc/secrets/.key";

vault.psk = "/etc/secrets/.psk";

generic-settings.configurationPath = lib.mkForce "/home/admin/luxnix";

generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "intel";

generic-settings.linux.initrd.availableKernelModules = ["xhci_pci" "ahci" "nvme" "usb_storage" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["nfs"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs"];
generic-settings.linux.kernelModules = ["kvm-intel"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["btrfs"];
generic-settings.systemStateVersion = "23.11";

generic-settings.vpnIp = "172.16.255.102";

nvidia-prime.nvidiaBusId = "PCI:1:0:0";

nvidia-prime.onboardBusId = "PCI:0:2:0";

nvidia-prime.onboardGpuType = "intel";

};
}