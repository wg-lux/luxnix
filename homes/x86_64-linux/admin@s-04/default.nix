# /default.nix
_: {
  cli = {
    programs = {
      git = {
        allowedSigners = "SHA256:LNfWnvEthO0QL8DzUxtxHD4VnLxvCZWFmcDhZodk29o";
        enable = true;
        email = "tlux14@googlemail.com";
        userName = "maddonix";
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
      language = "english";
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
  };

  home.stateVersion = "23.11";
}
