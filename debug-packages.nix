{ pkgs, lib, config, ... }:

let
  # Same detection logic as in custom-packages (updated)
  podmanEnabled = config.services.luxnix.podman.enable or config.services.virtualisation.podman.enable or config.luxnix.generic-settings.virtualization.enable or false;
  nvidiaEnabled = (config.luxnix.nvidia-default.enable or false) || (config.luxnix.nvidia-prime.enable or false) || (config.luxnix.generic-settings.gpu.nvidia.enable or false);
  
  debugInfo = {
    podmanEnabled = podmanEnabled;
    nvidiaEnabled = nvidiaEnabled;
    bothEnabled = podmanEnabled && nvidiaEnabled;
    servicesLuxnixPodman = config.services.luxnix.podman.enable or "not-set";
    servicesVirtualisationPodman = config.services.virtualisation.podman.enable or "not-set";
    genericSettingsVirtualization = config.luxnix.generic-settings.virtualization.enable or "not-set";
    nvidiaDefault = config.luxnix.nvidia-default.enable or "not-set";
    nvidiaPrime = config.luxnix.nvidia-prime.enable or "not-set";
    genericSettingsNvidia = config.luxnix.generic-settings.gpu.nvidia.enable or "not-set";
  };
in
{
  environment.systemPackages = [
    (pkgs.writeTextFile {
      name = "debug-packages-info";
      text = builtins.toJSON debugInfo;
      destination = "/bin/debug-packages-info";
      executable = true;
    })
  ];
}
