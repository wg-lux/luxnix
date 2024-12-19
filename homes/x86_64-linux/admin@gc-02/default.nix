{pkgs, ...}: {
  # cli.programs.git.allowedSigners = ; #TODO

  cli.programs.git = {
    enable = true;
    userName = "maxhild";
    email = "Maxhild10@gmail.com";
    allowedSigners = " SHA256:ZgT99una6mLioe2PAoNBEoHGmIlxwiu7/gB9B5J/BqI ";
  };

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
    gpu.enable = true;
    video.enable = true;
  };

  home.stateVersion = "23.11";
}
