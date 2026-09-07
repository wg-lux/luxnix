# /default.nix
_: {
  cli = {
    programs = {
      git = {
        allowedSigners = "";
        enable = true;
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
