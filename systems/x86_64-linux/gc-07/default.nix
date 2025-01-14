# gc-07/default.nix

{ config, pkgs, lib, modulesPath, ... }:

{
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
    ./boot-decryption-config.nix
    ./disks.nix
    ( import ./luxnix.nix { inherit config pkgs; } )
    ( import ./endoreg.nix { inherit config pkgs; } )
    ( import ./roles.nix { inherit config pkgs; } )
  ];

  boot.kernelPackages = pkgs.linuxPackages_latest;

  user = {
    admin = {
      name = "admin";
    };
    ansible.enable = true;
    settings.mutable = false;
  };

  roles = { 
    endoreg-client.enable = true;
    };

  services = {
    };

  luxnix = {
    generic-settings.configurationPathRelative = "lx-production";

generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "intel";

generic-settings.linux.initrd.availableKernelModules = ["vmd" "xhci_pci" "ahci" "nvme" "usb_storage" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["nfs"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs"];
generic-settings.linux.kernelModules = ["intel"];
generic-settings.linux.kernelModulesBlacklist = [];
# generic-settings.linux.kernelPackages = pkgs.linuxPackages_latest;

generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["btrfs"];
generic-settings.systemStateVersion = "23.11";

nvidia-prime.nvidiaBusId = "PCI:1:0:0";

nvidia-prime.nvidiaDriver = "beta";

nvidia-prime.onboardBusId = "PCI:0:2:0";

nvidia-prime.onboardGpuType = "intel";

};
}