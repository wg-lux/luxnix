{config, pkgs, lib, ...}@inputs:

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

      configurationPath = lib.mkForce "/home/admin/dev/luxnix";
      # sensitiveServiceGroupName = "sensitive-service-group"; # is default

      # sensitiveServiceGID = 901; # is default

      # Default
      # postgres = rec {
      #   defaultAuthentication = ''
      #       #type database                  DBuser                      address                     auth-method         optional_ident_map
      #       local sameuser                  all                                                     peer                map=superuser_map
      #   '';
      #   activeAuthentication = config.luxnix.generic-settings.postgres.defaultAuthentication;
      #   defaultIdentMap = ''
      #     # ArbitraryMapName systemUser DBUser
      #     superuser_map      root      postgres
      #     superuser_map      root      ${config.roles.postgres.default.replUser}
      #     superuser_map      ${config.user.admin.name}     postgres
      #     superuser_map      postgres  postgres
      #   '';
      #   activeIdentMap = config.luxnix.generic-settings.postgres.defaultIdentMap;
      # };

      # sslCertificateKeyPath = "${systemConfigurationPath}/ssl/cert.key";
      # sslCertificatePath = "${systemConfigurationPath}/ssl/cert.pem";

        
      linux = {
        cpuMicrocode = "intel"; # default is "intel"
        # processorType = "x86_64"; # default
        kernelPackages = pkgs.linuxPackages_latest; # default
        kernelModules = [ "kvm-intel" ];
        extraModulePackages = []; # default
        initrd = {
          kernelModules = ["dm-snapshot" ]; # default
          availableKernelModules = [ 
            "vmd" "xhci_pci" "ahci" "nvme" 
            "usb_storage" "sd_mod"
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