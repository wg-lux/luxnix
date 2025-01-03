{config, pkgs, ...}@inputs:

{
  luxnix = {
    traefik-host.enable = true;

    nvidia-prime = {
      enable = false; # enables common and desktop (with addon plasma) roles
    };

    generic-settings = {
      enable = true;
      hostPlatform = "x86_64-linux"; # is default
        
      linux = {
        cpuMicrocode = "amd"; # default is "intel"
        kernelPackages = pkgs.linuxPackages_latest; # default
        kernelModules = [ "kvm-amd" ];
        extraModulePackages = []; # default
        initrd = {
          supportedFilesystems = ["nfs"]; # default
          kernelModules = [ "nfs" "dm-snapshot" ]; # default
          availableKernelModules = [ "xhci_pci" "ahci" "mpt3sas" "usb_storage" "usbhid" "sd_mod" ];
        };

        supportedFilesystems = ["btrfs"]; # default
        resumeDevice = "/dev/disk/by-label/nixos"; # default
        kernelParams = []; # default
        
        blacklistedKernelModules = []; # default

        
    
      };
    };
  };
}