{pkgs, ...}: {
    cli.programs.git = {
      enable = true;
    };

  desktops = {
    plasma = {
      enable = true;
    };
  };

  services.luxnix = {
    # syncthing.enable = false;
  };

  luxnix.generic-settings = {
    enable = true;
    configurationPath = "dev/luxnix";
  };

  roles = {
    development.enable = true;
    social.enable = true;
    gpu.enable = true;
    video.enable = true;
  };

  home.stateVersion = "23.11";
}
