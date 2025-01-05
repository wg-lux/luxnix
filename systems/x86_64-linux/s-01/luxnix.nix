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
          ];
          availableKernelModules = [ 
            "xhci_pci"  
            "uas"  
            "ahci"  
            "usbhid"  
            "nvme"  
            "usb_storage"  
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