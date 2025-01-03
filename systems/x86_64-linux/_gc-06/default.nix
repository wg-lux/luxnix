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

  services = {};
  
  luxnix.nvidia-prime = {
    enable = true; # enables common and desktop (with addon plasma) roles
    nvidiaBusId = "PCI:1:0:0";
    onboardBusId = "PCI:0:2:0";
    onboardGpuType = "intel";
    nvidiaDriver = "beta";
  };

  #TODO Remove after prototyping ############################################
  luxnix.traefik-host.enable = true;
  networking.firewall = {
    allowedTCPPorts = [ 8300 80 443 ];
    allowedUDPPorts = [ 53 ];
  };

  luxnix.hardware.processorType = "intel";

  # services.luxnix.keycloak = {
  #   enable = true;
  #   vpnIP = "172.16.255.106";
  #   # port = 8080;

  #   hostname = "keycloak.endo-reg.net";
  # };

  programs.coolercontrol.enable = true;

  roles = {
    # desktop.enable = true;
    gpu-client-dev.enable = true;   # Enables common, desktop(with plasma) and laptop-gpu roles                                # Also enables aglnet.client.enable = true;
    postgres.main.enable = false;
    # ada.enable = true;

    # Testing
  };

  endoreg = {
    sensitive-storage = {
      enable = true; 
      partitionConfigurations = (import ./sensitive-storage.nix {} );
    };
  };

  user = {
    admin = {
      name = "admin";
    };
    ansible.enable = true;
    settings.mutable = false;
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
