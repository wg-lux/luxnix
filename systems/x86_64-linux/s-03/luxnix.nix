{config, pkgs, ...}@inputs:

{
  luxnix = {
    traefik-host.enable = true;

    nvidia-prime = {
      enable = true; # enables common and desktop (with addon plasma) roles
      nvidiaBusId = "";
      onboardBusId = "";
      onboardGpuType = "";
      nvidiaDriver = "";
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