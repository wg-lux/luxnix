{config, pkgs, ...}@inputs:

{
  luxnix = {
    traefik-host.enable = true;

    nvidia-prime = {
      enable = true; # enables common and desktop (with addon plasma) roles
      nvidiaBusId = "PCI:1:0:0";
      onboardBusId = "PCI:0:2:0";
      onboardGpuType = "intel";
      nvidiaDriver = "beta";
    };

    generic-settings = {
      enable = true;
      hostPlatform = "x86_64-linux"; 
        
      linux = {
        cpuMicrocode = "intel"; 
        kernelPackages = pkgs.pkgs.linuxPackages_latest; 
        kernelModules = [ 
          "kvm-intel" 
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
            "ahci"  
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