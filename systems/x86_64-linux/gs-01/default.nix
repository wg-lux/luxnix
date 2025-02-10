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
    ssh-access.dev-03.enable = true;
    ssh-access.dev-03.idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDBJcYjGNIwOUs+KG8TbBxPWtJFEqni0p+1J5Yz++Aos";
    };

  services = {
    };

  luxnix = {
    dns.enable = true;

generic-settings.adminVpnIp = "172.16.255.106";

generic-settings.enable = true;

generic-settings.language = "english";

generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;

generic-settings.network.keycloak.adminDomain = "adminKeycloak.endo-reg.net";

generic-settings.network.keycloak.domain = "keycloak.endo-reg.net";

generic-settings.network.keycloak.port = 8443;

generic-settings.network.keycloak.vpnIp = "172.16.255.12";

generic-settings.network.nextcloud.domain = "cloud.endo-reg.net";

generic-settings.network.nextcloud.port = 8444;

generic-settings.network.nextcloud.vpnIp = "172.16.255.21";

generic-settings.network.nginx.vpnIp = "172.16.255.12";

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

maintenance.autoUpdates.dates = "06:00";

maintenance.autoUpdates.enable = true;

maintenance.autoUpdates.flake = "github:wg-lux/luxnix";

maintenance.autoUpdates.operation = "switch";

nvidia-default.enable = true;

vault.dir = "/etc/secrets/vault";

vault.enable = true;

vault.key = "/etc/secrets/.key";

vault.psk = "/etc/secrets/.psk";

boot-decryption-stick-gs-01.enable = true;

generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "amd";

generic-settings.linux.initrd.availableKernelModules = ["xhci_pci" "ahci" "mpt3sas" "usb_storage" "usbhid" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["nfs" "dm-snapshot"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs"];
generic-settings.linux.kernelModules = ["kvm-amd"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["btrfs"];
generic-settings.systemStateVersion = "23.11";

generic-settings.vpnIp = "172.16.255.21";

};
}