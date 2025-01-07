{
  pkgs,
  lib,
  ...
}@inputs: 
  let
    sensitiveHdd = import ./sensitive-hdd.nix {};

    extraImports = [
      ./boot-decryption-config.nix
    ];

  in
{
  imports = [
    ./hardware-configuration.nix
    ./disks.nix
  ]++extraImports;

  # environment.pathsToLink = [
  #   "/share/fish"
  # ];
  systemd.services.NetworkManager-wait-online.enable = lib.mkForce false;
  systemd.services.systemd-networkd-wait-online.enable = lib.mkForce false;

  security.rtkit.enable = true;

  services = {
    virtualisation.kvm.enable = false;
    hardware.openrgb.enable = false;
    luxnix = {      
      ollama.enable = false;
      nfs.enable = false; #CHANGEME
    };
  };
  
  
  luxnix.nvidia-default.enable = true;
  luxnix.boot-decryption-stick-gs-02.enable = true;

  programs.coolercontrol.enable = true;

  roles = {
    gpu-server.enable=true;
  };

  endoreg = {
    sensitive-storage = {
      enable = false; 
      # partitionConfigurations = (import ./sensitive-storage.nix {} );
    };
  };

  # add admin@gc-02 public key
  roles.ssh-access.dev-01.enable = true; # defaults to give gc-02 ssh access

  user = {
    admin = {
      name = "admin";
    };
    dev-01 = { # enabled by default
      name = "dev-01";
    };
    user = { # enabled by default
      enable = true;
      name = "user";
    };
  };

  user.settings.mutable = false;


  boot = {
    kernelParams = [
      # "resume_offset=533760"
    ];
    blacklistedKernelModules = [
      # "ath12k_pci"
      # "ath12k"
    ];

    supportedFilesystems = lib.mkForce ["btrfs"];
    kernelPackages = pkgs.linuxPackages_latest;
    resumeDevice = "/dev/disk/by-label/nixos";

    initrd = {
      supportedFilesystems = ["nfs"];
      kernelModules = ["nfs"];
    };
  };

  system.stateVersion = "23.11";
}
