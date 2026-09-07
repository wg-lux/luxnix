# /default.nix
_: {
  luxnix = {
    generic-settings = {
      enable = true;
      hostPlatform = "x86_64-linux";
    };
  };

  home.stateVersion = "23.11";
}
