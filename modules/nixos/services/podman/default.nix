{config, lib, pkgs, ...}: 

with lib; 
with lib.luxnix; let
  cfg = config.services.luxnix.podman;
  adminUser = config.user.admin.name;
  cudaSupport = config.luxnix.nvidia-default.enable;
in {
  options.services.luxnix.podman = {
    enable = mkBoolOpt false "Enable Podman";
    # Enable podman-compose
    podmanCompose = mkBoolOpt false "Enable podman-compose";
    # Enable podman-docker
    dockerDropIn = mkBoolOpt true "Enable podman as docker drop-in replacement";
    nvidia = mkBoolOpt cudaSupport "Enable NVIDIA support";
    networkSocket = mkBoolOpt false "Enable network socket";
    extraPackages = mkOpt (types.listOf types.package) [] "Additional packages to install";
    autoPrune = mkBoolOpt true "Enable auto-prune";
    autoPruneFlags = mkOpt (types.listOf types.str) ["--all"] "Flags for auto-prune";
  };

  config = mkIf cfg.enable {

    users.users.${config.user.admin.name} = {
      extraGroups = [ "podman" ];
    };

    hardware.nvidia-container-toolkit.enable = cfg.nvidia;
    
    # Enable common container config files in /etc/containers
    virtualisation.containers.enable = true;
    virtualisation = {
      podman = {
        enable = cfg.enable;
        # Create a `docker` alias for podman, to use it as a drop-in replacement
        extraPackages = [] ++ cfg.extraPackages;
        dockerSocket.enable = cfg.dockerDropIn;
        dockerCompat = cfg.dockerDropIn;
        autoPrune = {
          enable = cfg.autoPrune;
          flags = cfg.autoPruneFlags;
        };
        # Required for containers under podman-compose to be able to talk to each other.
        # defaultNetwork.settings.dns_enabled = true;
        networkSocket = {
          enable = cfg.networkSocket;
          # tls.cert = "PATH_TO_CERT";
          # tls.key = "PATH_TO_KEY";
          # tls.cacert = "PATH_TO_CA_CERT";
          # server = "";
          port = 2376; # default
          openFirewall = false;
          listenAddress = "0.0.0.0"; # default
        };
      };
    };

    # users.users."${adminUser}".extraGroups = [ "podman" ];
  };
}