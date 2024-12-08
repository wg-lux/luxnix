{pkgs, ...}: {
  cli.programs.git.allowedSigners = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHwYnbv/tPCcTIPgFbOISXDOiGZGpyUtu6NmtJ+Pg9Dh agl-gpu-client-dev";

  desktops = {
    plasma = {
      enable = true;
    };
  };

  services.luxnix = {
    # syncthing.enable = false;
  };

  

  roles = {
    desktop.enable = true;
    social.enable = true;
    gpu.enable = true;
    video.enable = true;
  };

  luxnix.user = {
    enable = true;
    name = "admin";
  };

  home.stateVersion = "23.11";
}
