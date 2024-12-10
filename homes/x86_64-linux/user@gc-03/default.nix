{pkgs, ...}: {
  # cli.programs.git.allowedSigners = ; #TODO

  desktops = {
    plasma = {
      enable = true;
    };
  };

  services.luxnix = {
    # syncthing.enable = false;
  };

  roles = {
    desktop.enable = true;
    social.enable = true;
    gpu.enable = true;
    video.enable = true;
  };

  home.stateVersion = "23.11";
}
