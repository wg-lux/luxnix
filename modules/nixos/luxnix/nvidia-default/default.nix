{ config
, lib
, ...
}:

with lib;
with lib.luxnix; let
  cfg = config.luxnix.nvidia-default;

  nvidiaDrivers = {
    "stable" = config.boot.kernelPackages.nvidiaPackages.stable;
    "beta" = config.boot.kernelPackages.nvidiaPackages.beta;
    "production" = config.boot.kernelPackages.nvidiaPackages.production;

  };

in
{
  options.luxnix.nvidia-default = with types; {
    enable = mkBoolOpt false "Enable or disable the Nvidia GPU Support";

    enableCudaSupport = mkBoolOpt false "Enable CUDA support for nixpkgs package variants";
    enableOpenKernelModule = mkBoolOpt true "Enable Nvidia open kernel module (requires supported GPU)";

    nvidiaDriver = mkOption {
      type = types.enum [ "stable" "beta" "production" ];
      default = "production";
      description = "The nvidia driver to use";
    };
  };

  config = mkIf cfg.enable {

    hardware.graphics = {
      enable = true;
    };

    nixpkgs.config.cudaSupport = cfg.enableCudaSupport;

    services.xserver.videoDrivers = [ "nvidia" ];
    boot.initrd.kernelModules = [ "nvidia" ];
    hardware.nvidia = {
      modesetting.enable = true;
      powerManagement.enable = true;
      powerManagement.finegrained = false;
      open = cfg.enableOpenKernelModule;
      nvidiaSettings = true;
      package = nvidiaDrivers.${cfg.nvidiaDriver};
    };
  };

}
