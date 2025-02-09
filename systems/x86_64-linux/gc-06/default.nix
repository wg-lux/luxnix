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
    custom-packages.videoEditing = true;
    custom-packages.visuals = true;
    };

  services = {
    };

  luxnix = {
    boot-decryption-stick.enable = true;

dns.enable = true;

generic-settings.adminVpnIp = "172.16.255.106";

generic-settings.configurationPathRelative = "lx-production";

generic-settings.enable = true;

generic-settings.language = "english";

generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;

generic-settings.network.keycloak.adminDomain = "keycloak-admin.endo-reg.net";

generic-settings.network.keycloak.domain = "keycloak.endo-reg.net";

generic-settings.network.keycloak.port = 8443;

generic-settings.network.keycloak.vpnIp = "172.16.255.12";

generic-settings.network.nextcloud.domain = "cloud.endo-reg.net";

generic-settings.network.nextcloud.port = 8444;

generic-settings.network.nextcloud.vpnIp = "172.16.255.12";

generic-settings.network.psqlMain.domain = "psql-main.endo-reg.net";

generic-settings.network.psqlMain.port = 5432;

generic-settings.network.psqlMain.vpnIp = "172.16.255.12";

generic-settings.network.psqlTest.domain = "psql-test.endo-reg.net";

generic-settings.network.psqlTest.port = 5432;

generic-settings.network.psqlTest.vpnIp = "172.16.255.13";

generic-settings.postgres.enable = true;

generic-settings.sensitiveServiceGroupName = "sensitiveServices";

generic-settings.traefikHostDomain = "traefik.endo-reg.net";

generic-settings.traefikHostIp = "172.16.255.12";

generic-settings.vpnSubnet = "172.16.255.0/24";

gpu-eval.enable = true;

maintenance.autoUpdates.dates = "09:00";

maintenance.autoUpdates.enable = false;

maintenance.autoUpdates.flake = "github:wg-lux/luxnix";

maintenance.autoUpdates.operation = "switch";

nvidia-prime.enable = true;

nvidia-prime.nvidiaDriver = "beta";

vault.dir = "/etc/secrets/vault";

vault.enable = true;

vault.key = "/etc/secrets/.key";

vault.psk = "/etc/secrets/.psk";

generic-settings.configurationPath = lib.mkForce "/home/admin/dev/luxnix";

generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "intel";

generic-settings.linux.extraModulePackages = [];
generic-settings.linux.initrd.availableKernelModules = ["vmd" "xhci_pci" "ahci" "nvme" "usb_storage" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["dm-snapshot" "nfs" "btrfs"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.linux.kernelModules = ["kvm-intel"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["btrfs" "nfs"];
generic-settings.systemStateVersion = "23.11";

generic-settings.vpnIp = "172.16.255.106";

nvidia-prime.nvidiaBusId = "PCI:1:0:0";

nvidia-prime.onboardBusId = "PCI:0:2:0";

nvidia-prime.onboardGpuType = "intel";

};
}