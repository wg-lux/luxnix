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
    development.enable = true;
    social.enable = true;
    gpu.enable = false;
    video.enable = true;
  };

  home.stateVersion = "23.11";
}
