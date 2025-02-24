{ pkgs, ... }: {
  cli.programs.git = {
    enable = true;
    # userName = "maxhild";
    # email = "maxhild10@gmail.com";
    # allowedSigners = "SHA256:LNfWnvEthO0QL8DzUxtxHD4VnLxvCZWFmcDhZodk29o";
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
    # language = "english";
  };

  roles = {
    development.enable = true;
    social.enable = true;
    #"gpu.enable = true;"
    #"video.enable = true;"
  };

  home.stateVersion = "23.11";
}
