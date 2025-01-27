{pkgs, ...}: {
    cli.programs.git = {
      enable = true;
<<<<<<< HEAD
      userName = "maddonix";
      email = "tlux14@googlemail.com";
=======
      userName = "maxhild";
      email = "maxhild10@gmail.com";
>>>>>>> 6c76fda (gc-02 home)
      allowedSigners = "SHA256:LNfWnvEthO0QL8DzUxtxHD4VnLxvCZWFmcDhZodk29o";
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
<<<<<<< HEAD
    configurationPath = "luxnix";
=======
    configurationPath = "dev/luxnix";
>>>>>>> 6c76fda (gc-02 home)
  };

  roles = {
    development.enable = true;
    social.enable = true;
<<<<<<< HEAD
    gpu.enable = true;
    video.enable = true;
=======
    #"gpu.enable = true;"
    #"video.enable = true;"
>>>>>>> 6c76fda (gc-02 home)
  };

  home.stateVersion = "23.11";
}
