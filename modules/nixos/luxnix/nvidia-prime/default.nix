{ config
, inputs
, pkgs
, lib
, ...
}:

with lib;
with lib.luxnix; let
  cfg = config.luxnix.nvidia-prime;

in
{
  options.luxnix.nvidia-prime = with types; {
    enable = mkBoolOpt false "Enable or disable the Nvidia GPU Support";

    # Other bool options are: enable cuda support for nix packages, add xserver driver, add initrd-kernel-module, addd autoadddriverrunpath
    # enable prime sync, enable modesetting, 

    # input for nvidia, intel and amd busid
    nvidiaBusId = mkOption {
      type = types.str;
      default = "PCI:01:00:0";
      description = "The bus id of the nvidia gpu";
    };

    onboardBusId = mkOption {
      type = types.str;
      default = "PCI:00:02:0";
      description = "The bus id of the onboard gpu";
    };

    onboardGpuType = mkOption {
      type = types.str;
      default = "intel";
      description = "The onboard gpu (intel or amd or none)";
    };

    nvidiaDriver = mkOption {
      type = types.str;
      default = "beta";
      description = "The nvidia driver to use";
    };
  };

  config = mkIf cfg.enable {

    hardware.graphics = {
      enable = true;
    };

    nixpkgs.config.cudaSupport = true;

    services.xserver.videoDrivers = [ "nvidia" ];
    hardware.nvidia-container-toolkit.enable = lib.mkDefault true;
    hardware.nvidia = {

      prime = {
        sync.enable = true;
        nvidiaBusId = cfg.nvidiaBusId;
        "${cfg.onboardGpuType}BusId" = cfg.onboardBusId;
      };
      modesetting.enable = true;
      nvidiaSettings = true;

      powerManagement.enable = true;
      powerManagement.finegrained = false;
      open = lib.mkForce false;

      package = config.boot.kernelPackages.nvidiaPackages.production;

      gsp.enable = false; # GSP disabled is supposed to solve sleep issues on laptops

    };
    boot.extraModprobeConfig = ''
        options nvidia NVreg_EnableGpuFirmware=0
    '';
  };

}
