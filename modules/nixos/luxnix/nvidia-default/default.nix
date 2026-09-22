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

  nvidiaDrivers = {
    "stable" = config.boot.kernelPackages.nvidiaPackages.stable;
    "beta" = config.boot.kernelPackages.nvidiaPackages.beta;
    "production" = config.boot.kernelPackages.nvidiaPackages.production;

  };

in
{
  options.luxnix.nvidia-default = with types; {
    enable = mkBoolOpt false "Enable or disable the Nvidia GPU Support";

    # Other bool options are: enable cuda support for nix packages, add xserver driver, add initrd-kernel-module, addd autoadddriverrunpath
    # enable prime sync, enable modesetting,

    nvidiaDriver = mkOption {
      type = types.str;
      default = "production";
      description = "The nvidia driver to use";
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
      # mkDefault so a host that also enables luxnix.nvidia-prime (which pins the
      # production driver) wins without an option-merge conflict; NixOS 26.05
      # makes hardware.nvidia.package strictly unique.
      # package = mkDefault nvidiaDrivers.${cfg.nvidiaDriver};
      nvidiaPersistenced = true;
      package = config.boot.kernelPackages.nvidiaPackages.beta;
    };
  };

}
