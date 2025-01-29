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
    ssh-access.dev-01.enable = false;
    ssh-access.dev-01.idEd25519 = TODO;
    ssh-access.dev-03.enable = true;
    ssh-access.dev-03.idEd25519 = ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDBJcYjGNIwOUs+KG8TbBxPWtJFEqni0p+1J5Yz++Aos;
    };

  services = {
    };

  luxnix = {
    generic-settings.enable = true;

generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;

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

};
}