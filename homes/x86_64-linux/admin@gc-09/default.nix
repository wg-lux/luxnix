{ pkgs, ... }: {
  cli.programs.git = {
    enable = true;
    userName = "maddonix";
    email = "tlux14@googlemail.com";
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
    configurationPath = "lx-production";
  };

  roles = {
    development.enable = true;
    social.enable = true;
    gpu.enable = true;
    video.enable = true;
  };

  home.stateVersion = "23.11";
}
