{
  config,
  pkgs,
  lib,
  ...
}:

with lib;
with lib.luxnix;
let
  cfg = config.luxnix.nvidia-default;

in
{
  options.luxnix.nvidia-default = with types; {
    enable = mkBoolOpt false "Enable or disable the Nvidia GPU Support";

    # Other bool options are: enable cuda support for nix packages, add xserver driver, add initrd-kernel-module, addd autoadddriverrunpath
    # enable prime sync, enable modesetting,

    nvidiaDriver = mkOption {
      type = types.enum [
        "stable"
        "beta"
        "production"
      ];
      default = config.luxnix.generic-settings.gpu.nvidia.driver;
      description = "NVIDIA driver branch; inherits the shared GPU selection unless explicitly overridden.";
    };
  };

  config = mkIf cfg.enable {

    hardware.graphics = {
      enable = true;
      extraPackages = with pkgs; [
        triton-llvm
        nvidia-vaapi-driver
      ];
    };

    nixpkgs.config.cudaSupport = true;

    services.xserver.videoDrivers = [ "nvidia" ];
    boot.initrd.kernelModules = [ "nvidia" ];
    hardware.nvidia = {
      modesetting.enable = true;
      powerManagement.enable = mkDefault false;
      powerManagement.finegrained = false;
      open = true;
      nvidiaSettings = true;
      # PRIME owns the package when both modules are enabled. Its assertion
      # requires matching branch selections; package options are unique.
      nvidiaPersistenced = true;
      package = mkDefault config.boot.kernelPackages.nvidiaPackages.${cfg.nvidiaDriver};
    };
  };

}
