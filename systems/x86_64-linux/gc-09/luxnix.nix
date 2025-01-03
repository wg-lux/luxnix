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
      hostPlatform = "x86_64-linux"; # is default
        
      linux = {
        cpuMicrocode = "amd"; # default is "intel"
        # processorType = "x86_64"; # default
        kernelPackages = pkgs.linuxPackages_latest; # default
        kernelModules = [ "kvm-amd" ];
        extraModulePackages = []; # default
        initrd = {
          supportedFilesystems = ["nfs"]; # default
          kernelModules = [ "nfs" ]; # default
          availableKernelModules =   [ "xhci_pci" "ahci" "nvme" "usb_storage" "sd_mod" ];
        };

        supportedFilesystems = ["btrfs"]; # default
        resumeDevice = "/dev/disk/by-label/nixos"; # default
        kernelParams = []; # default
        
        blacklistedKernelModules = []; # default 
      };
    };
  };
}