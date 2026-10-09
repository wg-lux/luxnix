# /default.nix
_: {
  cli = {
    programs = {
      git = {
        allowedSigners = " SHA256:nN5Ha+k2duMh/XZnKqa3Bs7jkUorUpsKzF+aqhTMMGg ";
        enable = true;
        email = "hamza.ukw@gmail.com";
        userName = "Hamzaukw";
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
