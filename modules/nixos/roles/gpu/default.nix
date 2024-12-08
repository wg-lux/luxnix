{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.gpu;
in {
  options.roles.gpu = with types; {
    enable = mkBoolOpt false "Enable the gpu suite";
  };

  config = mkIf cfg.enable {
    hardware.graphics = {
      enable = true;
      extraPackages = with pkgs; [
        mesa
      ];
    };

    luxnix.nvidia-prime = {
      enable = true;
      nvidiaBusId = "PCI:01:00:0";
      onboardBusId = "PCI:00:02:0";
      onboardGpuType = "intel";
      nvidiaDriver = "beta";
    };
    

  
  };
}
