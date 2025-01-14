{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.luxnix.generic-settings.linux;

in {
  options.luxnix.generic-settings.linux = { 
    kernelPackages = mkOption {
      type = types.raw;
      default = pkgs.linuxPackages_latest;
      description = "Use linuxPackages_lates by default";
    };
    kernelModules = mkOption {
      type = types.listOf types.str;
      description = "Default Kernel Modules";
    };
    extraModulePackages = mkOption {
      type = types.listOf types.package;
      default = [];
      description = "Extra Kernel Modules";
    };
    cpuMicrocode = mkOption {
      type = types.str;
      default = "intel";
      description = "Default CPU Microcode";
    };
    processorType = mkOption {
      type = types.str;
      default = "x86_64";
      description = "Default Processor Type";
    };
    supportedFilesystems = mkOption {
      type = types.listOf types.str;
      default = ["btrfs"];
    };
    resumeDevice = mkOption {
      type = types.str;
      default = "/dev/disk/by-label/nixos";
    };
    kernelParams = mkOption {
      type = types.listOf types.str;
      default = [ ];
      description = "Default Kernel Params";
    };
    kernelModulesBlacklist = mkOption {
      type = types.listOf types.str;
      default = [ ];
      description = "Default blacklisted Kernel Modules";
    };
    initrd = {
      supportedFilesystems = mkOption {
        type = types.listOf types.str;
        default = ["nfs"];
        description = "Default supported filesystems for initrd";
      };
      kernelModules = mkOption {
        type = types.listOf types.str;
        default = ["nfs"];
        description = "Default supported Kernel modules for initrd";
      };
      availableKernelModules = mkOption {
        type = types.listOf types.str;
        default = [  ];
        description = "Default available Kernel modules for initrd";
      };
    };
  };

  config = mkIf config.luxnix.generic-settings.enable {

    
    hardware.cpu."${cfg.cpuMicrocode}".updateMicrocode = lib.mkDefault config.hardware.enableRedistributableFirmware;
    
    boot = {
      kernelModules = cfg.kernelModules;
      extraModulePackages = cfg.extraModulePackages;
      kernelParams = cfg.kernelParams;
      kernelPackages = lib.mkDefault cfg.kernelPackages;
      supportedFilesystems = lib.mkDefault cfg.supportedFilesystems;
      resumeDevice = cfg.resumeDevice;
      blacklistedKernelModules = cfg.kernelModulesBlacklist;
      initrd = cfg.initrd;
    };
  };
}

