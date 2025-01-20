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
    endoreg-client.enable = true;
    custom-packages.baseDevelopment = true;
    custom-packages.cuda = true;
    custom-packages.office = true;
    custom-packages.videoEditing = true;
    custom-packages.visuals = true;
    };

  services = {
    };

  luxnix = {
    boot-decryption-stick.enable = true;

generic-settings.configurationPathRelative = "lx-production";

generic-settings.enable = true;

gpu-eval.enable = true;

nvidia-prime.enable = true;

nvidia-prime.nvidiaDriver = "beta";

generic-settings.configurationPath = lib.mkForce "/home/admin/dev/luxnix";

generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "intel";

generic-settings.linux.extraModulePackages = [];
generic-settings.linux.initrd.availableKernelModules = ["vmd" "xhci_pci" "ahci" "nvme" "usb_storage" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["dm-snapshot" "nfs" "btrfs"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.linux.kernelModules = ["kvm-intel"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.kernelPackages = pkgs.linuxPackages_latest;

generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["btrfs" "nfs"];
generic-settings.systemStateVersion = "23.11";

nvidia-prime.nvidiaBusId = "PCI:1:0:0";

nvidia-prime.onboardBusId = "PCI:0:2:0";

nvidia-prime.onboardGpuType = "intel";

};
}