{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.luxnix.generic-settings.linux;

in
{
  options.luxnix.generic-settings.linux = {
    rmemMax = mkOption {
      type = types.int;
      default = 1048576 * 2;
      description = "Default net.core.rmem_max";
    };
    wmemMax = mkOption {
      type = types.int;
      default = 1048576 * 2;
      description = "Default net.core.wmem_max (2MB)";
    };
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
      default = [ ];
      description = "Extra Kernel Modules";
    };
    cpuMicrocode = mkOption {
      type = types.str;
      default = "intel";
      description = "Default CPU Microcode";
    };
    supportedFilesystems = mkOption {
      type = types.listOf types.str;
      default = [ "btrfs" ];
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
        default = [ "nfs" ];
        description = "Default supported filesystems for initrd";
      };
      kernelModules = mkOption {
        type = types.listOf types.str;
        default = [ "nfs" ];
        description = "Default supported Kernel modules for initrd";
      };
      availableKernelModules = mkOption {
        type = types.listOf types.str;
        default = [ ];
        description = "Default available Kernel modules for initrd";
      };
    };
  };

  config = mkIf config.luxnix.generic-settings.enable {

    hardware.cpu."${cfg.cpuMicrocode}".updateMicrocode =
      lib.mkDefault config.hardware.enableRedistributableFirmware;

    boot = {
      inherit (cfg) kernelModules extraModulePackages kernelParams;
      kernelPackages = lib.mkDefault cfg.kernelPackages;
      supportedFilesystems = lib.mkDefault cfg.supportedFilesystems;
      inherit (cfg) resumeDevice;
      blacklistedKernelModules = cfg.kernelModulesBlacklist;
      inherit (cfg) initrd;
    };
  };
}
