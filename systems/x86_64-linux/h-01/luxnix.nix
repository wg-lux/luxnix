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
        # processorType = "x86_64"; # default
        kernelPackages = pkgs.linuxPackages_latest; # default
        kernelModules = [ "kvm-amd" ];
        extraModulePackages = []; # default
        initrd = {
          supportedFilesystems = ["nfs" "btrfs" "vfat" ]; # default
          kernelModules = [ "nfs" ]; # default
          availableKernelModules = [           ] ++ [ 
            "igb" 
            "ahci" 
            "nvme" 
            "xhci_hcd" 
            "ast" 
            "ccp" "usb_storage"
            "usbhid" "sd_mod" 
          ];

        };

        supportedFilesystems = ["btrfs"]; # default
        resumeDevice = "/dev/disk/by-label/nixos"; # default
        kernelParams = []; # default
        
        blacklistedKernelModules = []; # default

        
    
      };
    };
  };
}