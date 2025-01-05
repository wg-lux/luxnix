{config, pkgs, ...}@inputs:

{
  luxnix = {
    traefik-host.enable = true;

    nvidia-prime = {
      enable = false; # enables common and desktop (with addon plasma) roles
    };

    generic-settings = {
      enable = true;
      hostPlatform = "x86_64-linux"; 
      systemStateVersion = "23.11";
        
      linux = {
        cpuMicrocode = "amd"; 
        kernelPackages = pkgs.pkgs.linuxPackages_latest; 
        kernelModules = [ 
          "kvm-amd" 
        ];
        extraModulePackages = [ 
        ];
        initrd = {
          supportedFilesystems = [ 
            "nfs" 
          ];
          kernelModules = [ 
            "nfs"  
            "dm-snapshot" 
          ];
          availableKernelModules = [ 
            "xhci_pci"  
            "ahci"  
            "thunderbolt"  
            "nvme"  
            "usb_storage"  
            "usbhid"  
            "sd_mod" 
          ];
        };

        supportedFilesystems = [ 
          "btrfs" 
        ];
        resumeDevice = "/dev/disk/by-label/nixos"; 
        kernelParams = [ 
        ];  
        
        blacklistedKernelModules = [ 
        ];
      };
    };
  };
}