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
    custom-packages.baseDevelopment = true;
    custom-packages.videoEditing = true;
    custom-packages.visuals = true;
    };

  services = {
    };

  # create an extra user named "test-admin" which uses "/etc/secrets/vault/SCRT_local_password_admin_password_hash"
  # as hashed password file
  users.extraUsers.test-admin = {
    name = "test-admin";
    hashedPasswordFile = "/etc/secrets/vault/SCRT_local_password_admin_password_hash"; # take-@-pick-648 
    home = "/home/test-admin";
    extraGroups = [ "wheel" "networkmanager" ];
    isNormalUser = true;
  };

  luxnix = {
    boot-decryption-stick.enable = true;

generic-settings.configurationPathRelative = "lx-production";

generic-settings.enable = true;

generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;

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

nvidia-prime.nvidiaBusId = "PCI:1:0:0";

nvidia-prime.onboardBusId = "PCI:0:2:0";

nvidia-prime.onboardGpuType = "intel";

};
}