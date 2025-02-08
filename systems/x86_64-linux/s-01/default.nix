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
    aglnet.client.enable = lib.mkForce false;
    aglnet.host.enable = true;
    base-server.enable = true;
    endoreg-client.enable = false;
    };

  services = {
    };

  luxnix = {
    boot-decryption-stick.enable = true;

dns.enable = true;

generic-settings.adminVpnIp = "172.16.255.106";

generic-settings.enable = true;

generic-settings.language = "english";

generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;

generic-settings.network.keycloak.port = 8443;

generic-settings.network.keycloak.vpnIp = "172.16.255.12";

generic-settings.network.nextcloud.port = 8444;

generic-settings.network.nextcloud.vpnIp = "172.16.255.12";

generic-settings.network.psql-main.port = 5432;

generic-settings.network.psql-main.vpnIp = "172.16.255.12";

generic-settings.network.psql-test.port = 5432;

generic-settings.network.psql-test.vpnIp = "172.16.255.13";

generic-settings.postgres.enable = true;

generic-settings.sensitiveServiceGroupName = "sensitiveServices";

generic-settings.traefikHostDomain = "traefik.endo-reg.net";

generic-settings.traefikHostIp = "172.16.255.12";

generic-settings.vpnSubnet = "172.16.255.0/24";

maintenance.autoUpdates.dates = "04:00";

maintenance.autoUpdates.enable = true;

maintenance.autoUpdates.flake = "github:wg-lux/luxnix";

nvidia-prime.enable = false;

vault.dir = "/etc/secrets/vault";

vault.enable = true;

vault.key = "/etc/secrets/.key";

vault.psk = "/etc/secrets/.psk";

generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "amd";

generic-settings.linux.initrd.availableKernelModules = ["xhci_pci" "uas" "ahci" "usbhid" "nvme" "usb_storage" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["nfs"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs"];
generic-settings.linux.kernelModules = ["kvm-amd"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["btrfs"];
generic-settings.systemStateVersion = "23.11";

generic-settings.vpnIp = "172.16.255.1";

};
}