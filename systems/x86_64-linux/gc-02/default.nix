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

  services.ssh = { # also enabled by endoreg-client role
    enable = true;
      authorizedKeys = [ # just adds authorized keys for admin user, does not enable ssh!
      "${config.luxnix.generic-settings.rootIdED25519}" 
      ];
    };

  roles = { 

    # endoreg-client.enable = true;
    aglnet.client.enable = true; # also enabled by endoreg-client role
    desktop.enable = true; # also enabled by endoreg-client role
    custom-packages.cuda = lib.mkForce true; # also enabled by endoreg-client role
    # also enables agl-admin ssh access

    custom-packages.baseDevelopment = true;
    };

  services = {
    };

  luxnix = {
    boot-decryption-stick.enable = true;

generic-settings.configurationPathRelative = "luxnix";

generic-settings.enable = true;

gpu-eval.enable = false;

maintenance.autoUpdates.dates = "09:00";

maintenance.autoUpdates.enable = false;

maintenance.autoUpdates.flake = "github:wg-lux/luxnix";

maintenance.autoUpdates.operation = "switch";

nvidia-prime.enable = lib.mkForce false; 

nvidia-prime.nvidiaDriver = "production";

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
generic-settings.linux.kernelPackages = pkgs.linuxPackages_latest;

generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["btrfs"];
generic-settings.systemStateVersion = "23.11";

nvidia-prime.nvidiaBusId = "PCI:1:0:0";

nvidia-prime.onboardBusId = "PCI:0:2:0";

nvidia-prime.onboardGpuType = "intel";

};
}