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
    };

  services = {
    };

  luxnix = {
    generic-settings.enable = true;

maintenance.autoUpdates.dates = "06:00";

maintenance.autoUpdates.enable = true;

maintenance.autoUpdates.flake = "github:wg-lux/luxnix";

maintenance.autoUpdates.operation = "update";

nvidia-default.enable = true;

boot-decryption-stick-gs-01.enable = true;

generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "amd";

generic-settings.linux.initrd.availableKernelModules = ["xhci_pci" "ahci" "thunderbolt" "nvme" "usb_storage" "usbhid" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["nfs" "btrfs" "dm-snapshot"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.linux.kernelModules = ["kvm-amd"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.kernelPackages = pkgs.linuxPackages_latest;

generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.systemStateVersion = "23.11";

};
}