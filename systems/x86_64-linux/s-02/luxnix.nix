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
        cpuMicrocode = "intel"; # default is "intel"
        # processorType = "x86_64"; # default
        kernelPackages = pkgs.linuxPackages_latest; # default
        kernelModules = [ "kvm-intel" ];
        extraModulePackages = []; # default
        initrd = {
          supportedFilesystems = ["nfs"]; # default
          kernelModules = [ "nfs" ]; # default
          availableKernelModules =  [ "xhci_pci" "ahci" "nvme" "usbhid" "usb_storage" "sd_mod" ];
        };

        supportedFilesystems = ["btrfs"]; # default
        resumeDevice = "/dev/disk/by-label/nixos"; # default
        kernelParams = []; # default
        
        blacklistedKernelModules = []; # default

        
    
      };
    };
  };
}