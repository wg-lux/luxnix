{
  pkgs,
  lib,
  ...
}@inputs: {
  imports = [
    ./hardware-configuration.nix
    ./disks.nix
  ];

  # environment.pathsToLink = [
  #   "/share/fish"
  # ];
  systemd.services.NetworkManager-wait-online.enable = lib.mkForce false;
  systemd.services.systemd-networkd-wait-online.enable = lib.mkForce false;

  security.rtkit.enable = true;
  services.pipewire.systemWide = true;
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;
    # If you want to use JACK applications, uncomment this
    # jack.enable = true;
  };

  
  services = {
    virtualisation.kvm.enable = false;
    hardware.openrgb.enable = false;
    luxnix.ollama.enable = false;
    luxnix.nfs.enable = false; #CHANGEME
  };

  programs.coolercontrol.enable = true;

  roles = {
    gpu.enable = true;
    desktop = {
      enable = true;
      # addons = {
      # };
    };
  };

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
