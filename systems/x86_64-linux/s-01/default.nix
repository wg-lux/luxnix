{
  pkgs,
  lib,
  ...
}@inputs: 
let
    extraImports = [
      ./boot-decryption-config.nix
    ];
in {
  imports = [
    ./hardware-configuration.nix
    ./disks.nix
  ] ++ extraImports;

  # environment.pathsToLink = [
  #   "/share/fish"
  # ];
  systemd.services.NetworkManager-wait-online.enable = lib.mkForce false;
  systemd.services.systemd-networkd-wait-online.enable = lib.mkForce false;

  security.rtkit.enable = true;


  services = {
    virtualisation.kvm.enable = false;
    hardware.openrgb.enable = false;
    luxnix.ollama.enable = false;
    luxnix.nfs.enable = false; #CHANGEME
  };
  
  luxnix.nvidia-prime.enable = false;

  programs.coolercontrol.enable = true;

  roles.aglnet.host.enable =true; # enables base-server (and base-server calls common and desktop)
  roles.base-server.enable=true;
  
  

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
