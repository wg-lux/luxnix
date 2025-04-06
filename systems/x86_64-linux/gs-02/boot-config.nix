{
  # Required kernel modules for our storage setup
  boot.initrd.availableKernelModules = [ 
    "dm-raid" "raid10" "sd_mod" "xhci_pci" "ahci" "nvme" 
  ];
  
  # Ensure kernel can find the right boot partition
  boot.loader.efi.canTouchEfiVariables = true;
  boot.loader.efi.efiSysMountPoint = "/boot";
  
  # Configure grub
  boot.loader.grub = {
    enable = true;
    device = "nodev";
    efiSupport = true;
    efiInstallAsRemovable = true;
    copyKernels = true;
    useOSProber = true;
    zfsSupport = false;
    extraEntries = ''
      menuentry "NixOS Fallback" {
        search --set=root --label boot
        configfile /boot/grub/grub.cfg
      }
    '';
  };
}
