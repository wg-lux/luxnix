# /default.nix
_: {
  cli = {
    programs = {
      git = {
        allowedSigners = "SHA256:LNfWnvEthO0QL8DzUxtxHD4VnLxvCZWFmcDhZodk29o";
        enable = true;
        email = "maxhild10@gmail.com";
        userName = "maxhild";
      };
    };
  };
  desktops = {
    plasma = {
      enable = true;
    };
  };
  luxnix = {
    generic-settings = {
      language = "german";
      configurationPath = "dev/luxnix";
      enable = true;
      hostPlatform = "x86_64-linux";
    };
  };
  roles = {
    development = {
      enable = true;
    };
    video = {
      enable = true;
    };
    gpu = {
      enable = true;
    };
    social = {
      enable = true;
    };
  };

  home.stateVersion = "23.11";
}
