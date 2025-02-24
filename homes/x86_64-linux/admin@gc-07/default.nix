{ pkgs, ... }: {
  cli.programs.git = {
    enable = true;
    userName = "PeterKczyk";
    email = "peter.kowalczyk21@gmail.com";
    # allowedSigners = "";
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
    language = "english";
  };

  roles = {
    development.enable = true;
    social.enable = true;
    gpu.enable = true;
    video.enable = true;
  };

  home.stateVersion = "23.11";
}
