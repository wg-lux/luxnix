{
  config,
  inputs,
  pkgs,
  lib,
  ...
}:

with lib;
with lib.luxnix; let
  cfg = config.luxnix.nvidia-prime;

  nvidiaDrivers = {
    "stable" = config.boot.kernelPackages.nvidiaPackages.stable;
    "beta" = config.boot.kernelPackages.nvidiaPackages.beta;
    "production" = config.boot.kernelPackages.nvidiaPackages.production;


    # Custom imports
    "555_58" = {
        version = "555.58";
        sha256_64bit = "sha256-bXvcXkg2kQZuCNKRZM5QoTaTjF4l2TtrsKUvyicj5ew=";
        sha256_aarch64 = pkgs.lib.fakeSha256;
        openSha256 = pkgs.lib.fakeSha256;
        settingsSha256 = "sha256-vWnrXlBCb3K5uVkDFmJDVq51wrCoqgPF03lSjZOuU8M=";
        persistencedSha256 = pkgs.lib.fakeSha256;
    };
  };

  # we need to find out what system we are working on (eg linux, darwin, ...)
  system = config.system.build.host.system;
  
in {
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
          extraPackages = with pkgs; [
            mesa
          ];
        };

    environment.systemPackages = [
      pkgs.autoAddDriverRunpath
    ];

    nixpkgs.config.cudaSupport = true;

    services.xserver.videoDrivers = ["nvidia"];
    boot.initrd.kernelModules = [ "nvidia" ];
    
    hardware.nvidia = {
      prime = {
        sync.enable = true;
        nvidiaBusId = cfg.nvidiaBusId;
        "${cfg.onboardGpuType}BusId" = cfg.onboardBusId;
      };

      modesetting.enable = true;
      powerManagement.enable = false;
      powerManagement.finegrained = false;
      open = false;
      nvidiaSettings = true;

      package = nvidiaDrivers."${cfg.nvidiaDriver}";
    };
  };
  
}